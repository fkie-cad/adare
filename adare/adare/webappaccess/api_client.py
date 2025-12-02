"""
API client for interacting with the ADARE Django backend API.

This module provides a high-level interface for publishing experiment runs,
checking experiment/run existence, and retrieving run details from the server.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Tuple

import requests
import aiohttp
import asyncio

import adare.config.server as config_server
from adare.webappaccess.exceptions import (
    NotLoggedInError,
    ExperimentNotFoundError,
    RunAlreadyExistsError,
    PublishPermissionError,
    ApiValidationError,
    ApiConnectionError,
)
from adare.webappaccess.login import WebappLogin, is_logged_in
from adare.database.api.serialize import SerializeApi

log = logging.getLogger(__name__)


class ApiClient:
    """
    Client for interacting with the ADARE backend API.

    Provides methods for publishing experiment runs and checking experiment/run status.
    All methods requiring authentication will check login status and raise NotLoggedInError
    if the user is not authenticated.
    """

    def __init__(self):
        self.login_handler = WebappLogin()

    @staticmethod
    def _files_to_request_files(files: dict) -> dict:
        """
        Convert file paths to request file format.

        Args:
            files: Dictionary mapping file keys to file paths

        Returns:
            Dictionary mapping file keys to (filename, content, mimetype) tuples
        """
        request_files = {}
        for name, path in files.items():
            if not Path(path).exists():
                log.warning(f'File {path} does not exist, skipping.')
                continue
            file_bytes = Path(path).read_bytes()
            request_files[name] = (Path(path).name, file_bytes, 'text/plain')
        return request_files

    def _get_auth_header(self) -> dict:
        """
        Get authentication header for Django API requests.

        Returns:
            Dictionary with Authorization header

        Raises:
            NotLoggedInError: If user is not logged in
        """
        if not is_logged_in():
            raise NotLoggedInError(
                log,
                'You are not logged in. Please log in first.',
                possible_solutions=['Run: adare web login']
            )
        return self.login_handler.get_django_authenticated_request_header()

    def publish_experiment_run(self, run_ulid: str) -> dict:
        """
        Publish an experiment run to the server.

        Args:
            run_ulid: ULID of the experiment run to publish

        Returns:
            Dictionary containing the created run data from the server

        Raises:
            NotLoggedInError: If user is not logged in
            ExperimentNotFoundError: If the experiment doesn't exist on server
            RunAlreadyExistsError: If the run already exists on server
            PublishPermissionError: If user lacks permission to publish
            ApiValidationError: If validation fails on server
            ApiConnectionError: If network/server error occurs
        """
        # Get serialized run data
        with SerializeApi() as api:
            data, files = api.serialize_run_by_ulid(run_ulid)

        # Convert file paths to request format
        request_files = self._files_to_request_files(files)

        # Get authentication header
        header = self._get_auth_header()

        # Make the request
        url = config_server.PUBLISH_RUN_URL
        try:
            response = requests.post(
                url,
                headers=header,
                data={'metadata': json.dumps(data)},
                files=request_files,
                timeout=config_server.TIMEOUT_SECONDS
            )
        except requests.exceptions.Timeout:
            raise ApiConnectionError(
                log,
                f'Request to {url} timed out',
                possible_solutions=['Check your network connection', 'Try again later']
            )
        except requests.exceptions.ConnectionError as e:
            raise ApiConnectionError(
                log,
                f'Failed to connect to server: {str(e)}',
                possible_solutions=['Check server URL in config', 'Verify server is running']
            )

        # Handle response
        if response.status_code == 201:
            log.info(f'Experiment run ({run_ulid}) published successfully.')
            return response.json()

        # Parse error response
        try:
            error_data = response.json()
            error_code = error_data.get('error', 'unknown')
            error_message = error_data.get('message', response.text)
        except (json.JSONDecodeError, AttributeError):
            error_code = 'unknown'
            error_message = response.text

        # Map error codes to specific exceptions
        if error_code == 'experiment_not_found':
            raise ExperimentNotFoundError(
                log,
                error_message,
                possible_solutions=['Publish the experiment first', 'Verify experiment ULID']
            )
        elif error_code == 'run_already_exists':
            raise RunAlreadyExistsError(
                log,
                error_message,
                possible_solutions=['Run already published, no action needed']
            )
        elif error_code == 'experiment_not_published':
            raise ExperimentNotFoundError(
                log,
                error_message,
                possible_solutions=['Publish the experiment before publishing runs']
            )
        elif error_code in ('gitea_user_not_found', 'environment_not_found'):
            raise PublishPermissionError(
                log,
                error_message,
                possible_solutions=['Contact administrator', 'Check your account setup']
            )
        elif error_code in ('validation_error', 'event_validation_error', 'missing_field'):
            raise ApiValidationError(
                log,
                f'{error_message}\nDetails: {error_data.get("details", "N/A")}',
                possible_solutions=['Check run data integrity', 'Report issue if persists']
            )
        else:
            raise ApiConnectionError(
                log,
                f'Publishing failed (status {response.status_code}): {error_message}',
                possible_solutions=['Check server logs', 'Try again later']
            )

    def check_experiment_exists(self, experiment_ulid: str) -> bool:
        """
        Check if an experiment exists on the server by ULID.

        Args:
            experiment_ulid: ULID of the experiment to check

        Returns:
            True if experiment exists and is published, False otherwise

        Raises:
            ApiConnectionError: If network/server error occurs
        """
        url = config_server.CHECK_EXPERIMENT_URL
        params = {'ulid': experiment_ulid}

        try:
            response = requests.get(url, params=params, timeout=config_server.TIMEOUT_SECONDS)
        except requests.exceptions.Timeout:
            raise ApiConnectionError(
                log,
                f'Request to {url} timed out',
                possible_solutions=['Check your network connection', 'Try again later']
            )
        except requests.exceptions.ConnectionError as e:
            raise ApiConnectionError(
                log,
                f'Failed to connect to server: {str(e)}',
                possible_solutions=['Check server URL in config', 'Verify server is running']
            )

        if response.status_code == 200:
            data = response.json()
            # Check if response contains a valid ULID and published status
            return bool(data.get('ulid')) and data.get('published', False)
        else:
            log.warning(f'Check experiment request failed with status {response.status_code}')
            return False

    def check_run_exists(self, run_ulid: str) -> bool:
        """
        Check if an experiment run exists on the server by ULID.

        Args:
            run_ulid: ULID of the experiment run to check

        Returns:
            True if run exists, False otherwise

        Raises:
            ApiConnectionError: If network/server error occurs
        """
        url = f'{config_server.API_URL}run/check/'
        params = {'ulid': run_ulid}

        try:
            response = requests.get(url, params=params, timeout=config_server.TIMEOUT_SECONDS)
        except requests.exceptions.Timeout:
            raise ApiConnectionError(
                log,
                f'Request to {url} timed out',
                possible_solutions=['Check your network connection', 'Try again later']
            )
        except requests.exceptions.ConnectionError as e:
            raise ApiConnectionError(
                log,
                f'Failed to connect to server: {str(e)}',
                possible_solutions=['Check server URL in config', 'Verify server is running']
            )

        if response.status_code == 200:
            data = response.json()
            return bool(data.get('ulid'))
        else:
            log.warning(f'Check run request failed with status {response.status_code}')
            return False

    def get_run_details(self, run_ulid: str) -> Optional[dict]:
        """
        Retrieve experiment run details from the server.

        Args:
            run_ulid: ULID of the experiment run

        Returns:
            Dictionary containing run details, or None if not found

        Raises:
            ApiConnectionError: If network/server error occurs
        """
        url = f'{config_server.API_URL}run/run_{run_ulid}/'

        try:
            response = requests.get(url, timeout=config_server.TIMEOUT_SECONDS)
        except requests.exceptions.Timeout:
            raise ApiConnectionError(
                log,
                f'Request to {url} timed out',
                possible_solutions=['Check your network connection', 'Try again later']
            )
        except requests.exceptions.ConnectionError as e:
            raise ApiConnectionError(
                log,
                f'Failed to connect to server: {str(e)}',
                possible_solutions=['Check server URL in config', 'Verify server is running']
            )

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 404:
            log.warning(f'Run {run_ulid} not found on server')
            return None
        else:
            raise ApiConnectionError(
                log,
                f'Failed to retrieve run details (status {response.status_code})',
                possible_solutions=['Check run ULID', 'Verify server is running']
            )


# Convenience functions for backward compatibility and simple usage

def publish_experiment_run(run_ulid: str) -> dict:
    """
    Publish an experiment run to the server.

    Args:
        run_ulid: ULID of the experiment run to publish

    Returns:
        Dictionary containing the created run data from the server
    """
    client = ApiClient()
    return client.publish_experiment_run(run_ulid)


def check_experiment_exists(experiment_ulid: str) -> bool:
    """
    Check if an experiment exists on the server.

    Args:
        experiment_ulid: ULID of the experiment to check

    Returns:
        True if experiment exists and is published, False otherwise
    """
    client = ApiClient()
    return client.check_experiment_exists(experiment_ulid)


def check_run_exists(run_ulid: str) -> bool:
    """
    Check if an experiment run exists on the server.

    Args:
        run_ulid: ULID of the experiment run to check

    Returns:
        True if run exists, False otherwise
    """
    client = ApiClient()
    return client.check_run_exists(run_ulid)

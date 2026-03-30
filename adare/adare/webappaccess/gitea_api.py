"""
Gitea REST API v1 client for creating branches, uploading files, and creating pull requests.
"""
import base64
import requests

import logging

log = logging.getLogger(__name__)


class GiteaApiClient:
    """Client for Gitea REST API v1 using user's OAuth token."""

    def __init__(self, gitea_base_url: str, token: str):
        self.api_url = f"{gitea_base_url}api/v1/"
        self.session = requests.Session()
        self.session.headers['Authorization'] = f'token {token}'

    def get_repo(self, owner: str, repo: str) -> dict:
        url = f'{self.api_url}repos/{owner}/{repo}'
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()

    def check_branch_exists(self, owner: str, repo: str, branch: str) -> bool:
        url = f'{self.api_url}repos/{owner}/{repo}/branches/{branch}'
        response = self.session.get(url)
        return response.status_code == 200

    def create_branch(self, owner: str, repo: str, branch_name: str, from_branch: str = 'main') -> bool:
        url = f'{self.api_url}repos/{owner}/{repo}/branches'
        data = {
            'new_branch_name': branch_name,
            'old_branch_name': from_branch,
        }
        response = self.session.post(url, json=data)
        if response.status_code == 201:
            log.info(f'Created branch {branch_name} from {from_branch}')
            return True
        log.error(f'Failed to create branch {branch_name}: {response.status_code} {response.text}')
        return False

    def create_or_update_file(self, owner: str, repo: str, filepath: str,
                               content_bytes: bytes, branch: str, message: str) -> bool:
        url = f'{self.api_url}repos/{owner}/{repo}/contents/{filepath}'
        content_b64 = base64.b64encode(content_bytes).decode('ascii')

        # Check if file already exists to get its SHA (needed for update)
        response = self.session.get(url, params={'ref': branch})
        data = {
            'message': message,
            'content': content_b64,
            'branch': branch,
        }
        if response.status_code == 200:
            existing = response.json()
            data['sha'] = existing['sha']

        response = self.session.put(url, json=data)
        if response.status_code in (200, 201):
            log.info(f'Uploaded {filepath} to {branch}')
            return True
        log.error(f'Failed to upload {filepath}: {response.status_code} {response.text}')
        return False

    def delete_file(self, owner: str, repo: str, filepath: str,
                     branch: str, sha: str, message: str) -> bool:
        url = f'{self.api_url}repos/{owner}/{repo}/contents/{filepath}'
        data = {
            'message': message,
            'sha': sha,
            'branch': branch,
        }
        response = self.session.delete(url, json=data)
        if response.status_code in (200, 204):
            log.info(f'Deleted {filepath} from {branch}')
            return True
        log.error(f'Failed to delete {filepath}: {response.status_code} {response.text}')
        return False

    def create_pull_request(self, owner: str, repo: str, title: str,
                             head: str, base: str = 'main', body: str = '') -> dict:
        url = f'{self.api_url}repos/{owner}/{repo}/pulls'
        data = {
            'title': title,
            'head': head,
            'base': base,
            'body': body,
        }
        response = self.session.post(url, json=data)
        response.raise_for_status()
        pr = response.json()
        log.info(f'Created PR #{pr["number"]}: {title}')
        return pr

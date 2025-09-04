"""
Test result logging utilities for adarevm.

This module handles test result logging on the VM side,
keeping concerns separated between VM and host processing.
"""

import logging
from typing import Any, List, Optional
from adarelib.constants import StatusEnum
from adarelib.event.event import TestResult

log = logging.getLogger(__name__)


class TestResultLogger:
    """Handles test result logging on the VM side."""
    
    @staticmethod
    def log_test_result(test_name: str, result: TestResult) -> None:
        """
        Log test result details on the VM side.
        
        Args:
            test_name: Name of the test that was executed
            result: TestResult object containing status and details
        """
        if not result:
            log.warning(f"Test '{test_name}' returned no result")
            return
        
        # Debug logging to understand the result object
        log.debug(f"Test '{test_name}' result object type: {type(result)}")
        log.debug(f"Test '{test_name}' result object attributes: {dir(result)}")
        log.debug(f"Test '{test_name}' result object: {result}")
        
        status = getattr(result, 'status', StatusEnum.NONE)
        details = getattr(result, 'details', [])
        
        # Additional debug for status
        log.debug(f"Test '{test_name}' extracted status: {status} (type: {type(status)})")
        
        # Log the primary result
        status_name = TestResultLogger._get_status_name(status)
        log.info(f"Test '{test_name}' result: {status_name}")
        
        # Log details if available
        if details:
            if isinstance(details, list):
                for detail in details:
                    log.info(f"Test '{test_name}' detail: {detail}")
            else:
                log.info(f"Test '{test_name}' details: {details}")
    
    @staticmethod
    def format_result_for_response(test_name: str, result: TestResult) -> dict:
        """
        Format test result for WebSocket response.
        
        Args:
            test_name: Name of the test
            result: TestResult object
            
        Returns:
            Dict containing formatted result data
        """
        if not result:
            return {
                'status': TestResultLogger._get_status_name(StatusEnum.NONE),
                'details': ['No result returned']
            }
        
        status = getattr(result, 'status', StatusEnum.NONE)
        details = getattr(result, 'details', [])
        
        return {
            'status': TestResultLogger._get_status_name(status),
            'details': details if isinstance(details, list) else [str(details)] if details else []
        }
    
    @staticmethod
    def _get_status_name(status: StatusEnum) -> str:
        """Convert StatusEnum to string name."""
        if status == StatusEnum.SUCCESS:
            return 'SUCCESS'
        elif status == StatusEnum.FAILED:
            return 'FAILED'
        elif status == StatusEnum.ERROR:
            return 'ERROR'
        elif status == StatusEnum.WARNING:
            return 'WARNING'
        else:
            return 'UNKNOWN'
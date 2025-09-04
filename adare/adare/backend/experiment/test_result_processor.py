"""
Test result processing utilities for the host side.

This module handles test result processing on the host side,
extracting and formatting results received from adarevm.
"""

import logging
from typing import Dict, Any, List
from adare.types.playbook import ActionResult

log = logging.getLogger(__name__)


class TestResultProcessor:
    """Handles test result processing on the host side."""
    
    # Test status constants (matching adarevm side)
    STATUS_SUCCESS = 'SUCCESS'
    STATUS_FAILED = 'FAILED' 
    STATUS_ERROR = 'ERROR'
    STATUS_WARNING = 'WARNING'
    STATUS_UNKNOWN = 'UNKNOWN'
    
    @classmethod
    def process_test_result(cls, test_name: str, ws_result: Dict[str, Any]) -> ActionResult:
        """
        Process test result received from WebSocket.
        
        Args:
            test_name: Name of the test that was executed
            ws_result: Result dictionary from WebSocket call
            
        Returns:
            ActionResult with processed test information
        """
        # Extract test result data from WebSocket response
        test_result_data = ws_result.get('result', {})
        test_status = test_result_data.get('status', cls.STATUS_UNKNOWN)
        test_details = test_result_data.get('details', [])
        
        # Log test result on host side
        cls._log_test_result(test_name, test_status, test_details)
        
        # Create detailed message
        base_message = ws_result.get('message', '')
        detailed_message = cls._create_detailed_message(base_message, test_status, test_details)
        
        # Determine overall success
        execution_success = ws_result.get('status') == 'success'
        test_success = test_status == cls.STATUS_SUCCESS
        overall_success = execution_success and test_success
        
        return ActionResult(
            success=overall_success,
            message=detailed_message,
            data=ws_result
        )
    
    @classmethod
    def _log_test_result(cls, test_name: str, status: str, details: List[str]) -> None:
        """Log test result details on host side."""
        log.info(f"Test '{test_name}' completed: {status}")
        
        if details:
            for detail in details:
                log.info(f"Test '{test_name}' detail: {detail}")
    
    @classmethod
    def _create_detailed_message(cls, base_message: str, status: str, details: List[str]) -> str:
        """Create a detailed message including test result information."""
        if status == cls.STATUS_UNKNOWN:
            return base_message
        
        if details:
            details_str = ', '.join(details)
            return f"{base_message} - Test result: {status}, Details: {details_str}"
        else:
            return f"{base_message} - Test result: {status}"
    
    @classmethod
    def is_success_status(cls, status: str) -> bool:
        """Check if a test status represents success."""
        return status == cls.STATUS_SUCCESS
    
    @classmethod
    def is_failure_status(cls, status: str) -> bool:
        """Check if a test status represents failure."""
        return status in [cls.STATUS_FAILED, cls.STATUS_ERROR]
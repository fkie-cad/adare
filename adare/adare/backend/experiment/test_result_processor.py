"""
Test result processing utilities for the host side.

This module handles test result processing on the host side,
extracting and formatting results received from adarevm.
"""

import logging
from typing import Dict, Any, List
from adare.backend.experiment.action_executor import ActionResult

log = logging.getLogger(__name__)


class TestResultProcessor:
    """Handles test result processing on the host side."""
    
    # Test status constants (matching adarevm side)
    STATUS_SUCCESS = 'SUCCESS'
    STATUS_FAILED = 'FAILED' 
    STATUS_ERROR = 'ERROR'
    STATUS_WARNING = 'WARNING'
    STATUS_UNKNOWN = 'UNKNOWN'
    
    # Error categorization for better reporting
    EXECUTION_ERRORS = {STATUS_ERROR}
    TEST_FAILURES = {STATUS_FAILED}
    SUCCESS_STATUSES = {STATUS_SUCCESS}
    
    @classmethod
    def process_test_result(cls, test_name: str, ws_result: Dict[str, Any], expect_to_fail: bool = False) -> ActionResult:
        """
        Process test result received from WebSocket.
        
        Args:
            test_name: Name of the test that was executed
            ws_result: Result dictionary from WebSocket call
            expect_to_fail: If True, invert SUCCESS/FAILED status (errors remain errors)
            
        Returns:
            ActionResult with processed test information
        """
        # Extract test result data from WebSocket response
        test_result_data = ws_result.get('result', {})
        test_status = test_result_data.get('status', cls.STATUS_UNKNOWN)
        test_details = test_result_data.get('details', [])
        
        # Categorize the result for better logging
        result_category = cls._categorize_result(test_status)
        
        # Apply expect_to_fail logic - only invert test success/failure, not execution errors
        modified_test_details = list(test_details)
        if expect_to_fail and ws_result.get('status') == 'success':
            # Only invert if the test actually executed (no execution errors)
            if test_status == cls.STATUS_SUCCESS:
                # Test succeeded but we expected it to fail
                test_success = False
                # Add note to details about expectation
                modified_test_details.append("Expected to fail but succeeded")
            elif test_status == cls.STATUS_FAILED:
                # Test failed but we expected it to fail - this is success
                test_success = True
                # Add note to details about expectation
                modified_test_details.append("Expected to fail and did fail")
            else:
                # For success/unknown status, use normal logic
                test_success = test_status in cls.SUCCESS_STATUSES
        else:
            # Normal logic when expect_to_fail is False or there was an execution error
            test_success = test_status in cls.SUCCESS_STATUSES
        
        # Log test result on host side with category (use modified details for logging)
        cls._log_test_result(test_name, test_status, modified_test_details, result_category)
        
        # Create detailed message with result category (use modified details)
        base_message = ws_result.get('message', '')
        detailed_message = cls._create_detailed_message(base_message, test_status, modified_test_details, result_category)
        
        # Determine overall success
        execution_success = ws_result.get('status') == 'success'
        overall_success = execution_success and test_success
        
        return ActionResult(
            success=overall_success,
            message=detailed_message,
            data={**ws_result, 'result_category': result_category, 'expect_to_fail': expect_to_fail}
        )
    
    @classmethod
    def _log_test_result(cls, test_name: str, status: str, details: List[str], category: str) -> None:
        """Log test result details on host side."""
        log.info(f"Test '{test_name}' completed: {status} ({category})")
        
        if details:
            for detail in details:
                if category == 'execution_error':
                    log.error(f"Test '{test_name}' execution error: {detail}")
                elif category == 'test_failure':
                    log.warning(f"Test '{test_name}' test failure: {detail}")
                else:
                    log.info(f"Test '{test_name}' detail: {detail}")
    
    @classmethod
    def _create_detailed_message(cls, base_message: str, status: str, details: List[str], category: str) -> str:
        """Create a detailed message including test result information."""
        if status == cls.STATUS_UNKNOWN:
            return base_message
        
        # Create category-specific message prefixes
        category_prefix = {
            'success': '✓',
            'test_failure': '✗', 
            'execution_error': '⚠'
        }.get(category, '')
        
        status_with_category = f"{category_prefix} {status}" if category_prefix else status
        
        if details:
            details_str = ', '.join(details)
            return f"{base_message} - Result: {status_with_category}, Details: {details_str}"
        else:
            return f"{base_message} - Result: {status_with_category}"
    
    @classmethod
    def is_success_status(cls, status: str) -> bool:
        """Check if a test status represents success."""
        return status == cls.STATUS_SUCCESS
    
    @classmethod
    def is_failure_status(cls, status: str) -> bool:
        """Check if a test status represents failure (either test failure or execution error)."""
        return status in [cls.STATUS_FAILED, cls.STATUS_ERROR]
    
    @classmethod
    def is_execution_error(cls, status: str) -> bool:
        """Check if a test status represents an execution error."""
        return status in cls.EXECUTION_ERRORS
    
    @classmethod
    def is_test_failure(cls, status: str) -> bool:
        """Check if a test status represents a legitimate test failure."""
        return status in cls.TEST_FAILURES
    
    @classmethod
    def _categorize_result(cls, status: str) -> str:
        """Categorize test result for better handling and display."""
        if status in cls.SUCCESS_STATUSES:
            return 'success'
        elif status in cls.TEST_FAILURES:
            return 'test_failure'
        elif status in cls.EXECUTION_ERRORS:
            return 'execution_error'
        else:
            return 'unknown'
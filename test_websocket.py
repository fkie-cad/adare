#!/usr/bin/env python3
"""
Test script for WebSocket communication between host and adarevm.

This script tests the WebSocket server and client implementation.
"""

import asyncio
import logging
import sys
import json
from pathlib import Path

# Add paths for imports
sys.path.insert(0, str(Path(__file__).parent / "adare"))
sys.path.insert(0, str(Path(__file__).parent / "adarevm"))

from adare.backend.experiment.websocket_client import AdareVMClient

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)


async def test_basic_connection():
    """Test basic connection to adarevm server."""
    log.info("Testing basic connection...")
    
    try:
        async with AdareVMClient() as client:
            log.info("✓ Connection established")
            
            # Test ping
            ping_result = await client.ping()
            log.info(f"✓ Ping successful: {ping_result}")
            
            # Test get status
            status = await client.get_status()
            log.info(f"✓ Status: {status}")
            
            return True
            
    except Exception as e:
        log.error(f"✗ Connection test failed: {e}")
        return False


async def test_gui_actions():
    """Test GUI action commands."""
    log.info("Testing GUI actions...")
    
    try:
        async with AdareVMClient() as client:
            # Test screenshot
            screenshot_result = await client.screenshot()
            log.info(f"✓ Screenshot: {len(screenshot_result.get('image', {}).get('data', ''))} bytes")
            
            # Test click (safe coordinates)
            click_result = await client.click(100, 100)
            log.info(f"✓ Click: {click_result}")
            
            # Test keyboard
            keyboard_result = await client.keyboard("type", "test")
            log.info(f"✓ Keyboard: {keyboard_result}")
            
            # Test idle
            idle_result = await client.idle(0.5)
            log.info(f"✓ Idle: {idle_result}")
            
            return True
            
    except Exception as e:
        log.error(f"✗ GUI actions test failed: {e}")
        return False


async def test_event_handling():
    """Test event handling and streaming."""
    log.info("Testing event handling...")
    
    events_received = []
    
    def event_handler(event_type, data):
        events_received.append({"type": event_type, "data": data})
        log.info(f"Event received: {event_type} - {data}")
    
    try:
        client = AdareVMClient()
        client.add_event_handler('*', event_handler)
        
        await client.connect()
        
        # Perform an action that should generate events
        await client.click(50, 50)
        
        # Wait a bit for events
        await asyncio.sleep(1.0)
        
        await client.disconnect()
        
        log.info(f"✓ Received {len(events_received)} events")
        for event in events_received:
            log.info(f"  - {event['type']}: {event['data']}")
        
        return len(events_received) > 0
        
    except Exception as e:
        log.error(f"✗ Event handling test failed: {e}")
        return False


async def test_testset_workflow():
    """Test the complete testset workflow."""
    log.info("Testing testset workflow...")
    
    try:
        async with AdareVMClient() as client:
            # Test variables
            variables = {"test_var": "test_value", "number": 42}
            var_result = await client.set_variables(variables)
            log.info(f"✓ Variables set: {var_result}")
            
            # Test list tests (should be empty initially)
            list_result = await client.list_tests()
            log.info(f"✓ List tests: {list_result}")
            
            # Note: To fully test testset upload, we'd need actual testfunction files
            log.info("✓ Testset workflow basics working")
            
            return True
            
    except Exception as e:
        log.error(f"✗ Testset workflow test failed: {e}")
        return False


async def main():
    """Run all tests."""
    log.info("Starting WebSocket communication tests...")
    log.info("Make sure adarevm WebSocket server is running on localhost:13108")
    
    tests = [
        ("Basic Connection", test_basic_connection),
        ("GUI Actions", test_gui_actions), 
        ("Event Handling", test_event_handling),
        ("Testset Workflow", test_testset_workflow),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        log.info(f"\n--- Running {test_name} Test ---")
        try:
            result = await test_func()
            results.append((test_name, result))
            if result:
                log.info(f"✓ {test_name} test PASSED")
            else:
                log.warning(f"✗ {test_name} test FAILED")
        except Exception as e:
            log.error(f"✗ {test_name} test ERROR: {e}")
            results.append((test_name, False))
    
    # Summary
    log.info("\n--- Test Summary ---")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        log.info(f"{test_name}: {status}")
    
    log.info(f"\nTests passed: {passed}/{total}")
    
    if passed == total:
        log.info("🎉 All tests passed!")
        return 0
    else:
        log.warning(f"⚠️  {total - passed} tests failed")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        log.info("Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        log.error(f"Test runner error: {e}")
        sys.exit(1)
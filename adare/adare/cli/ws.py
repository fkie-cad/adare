"""
WebSocket CLI commands for adarevm interaction.
"""

import asyncio
import yaml
import json
import sys
import logging
from pathlib import Path
from typing import Dict, Any, List
from types import SimpleNamespace

from adare.backend.experiment.websocket_client import AdareVMClient, WebSocketTimeoutError
from adare.exceptions import LoggedException

log = logging.getLogger(__name__)

class WSActionError(LoggedException):
    """Error during WebSocket action execution."""
    def __init__(self, message: str):
        super().__init__(log, message)

async def exec_ws_action(args: SimpleNamespace):
    """Execute WebSocket actions from YAML file."""
    try:
        # Use provided host and port directly
        host = getattr(args, 'host', 'localhost')
        port = getattr(args, 'port', 18765)
        
        log.info(f"Connecting to adarevm at {host}:{port}")
        
        # Load action YAML
        action_file = Path(args.action_file)
        if not action_file.exists():
            raise WSActionError(f"Action file not found: {action_file}")
        
        try:
            with open(action_file, 'r') as f:
                actions_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise WSActionError(f"Invalid YAML in action file: {e}")
        
        # Validate YAML structure - support both playbook and simple action format
        if not isinstance(actions_data, dict):
            raise WSActionError("Action file must contain a YAML dictionary")
        
        # Check for playbook format (has 'actions' key) or simple action list
        if 'actions' in actions_data:
            actions = actions_data['actions']
        elif isinstance(actions_data, list):
            # Direct list of actions
            actions = actions_data
        else:
            raise WSActionError("Action file must contain an 'actions' key or be a list of actions")
        
        if not isinstance(actions, list):
            raise WSActionError("'actions' must be a list")
        
        # Connect to adarevm
        client = AdareVMClient(host=host, port=port)
        
        try:
            connected = await client.connect(timeout=args.connect_timeout)
            if not connected:
                raise WSActionError(f"Failed to connect to adarevm at {host}:{port}")
            
            log.info(f"Connected to adarevm server successfully")
            
            # Execute actions
            results = []
            for i, action in enumerate(actions):
                result = await execute_single_action(client, action, i+1, args)
                results.append(result)
                
                # Stop on first error if not in continue mode
                if not args.continue_on_error and result.get('status') == 'error':
                    log.error(f"Action {i+1} failed, stopping execution")
                    break
            
            # Output results
            output_results(results, args.output_format)
            
        finally:
            await client.disconnect()
            
    except Exception as e:
        log.error(f"WebSocket action execution failed: {e}")
        raise WSActionError(str(e))

async def execute_single_action(client: AdareVMClient, action: Dict[str, Any], 
                               action_num: int, args: SimpleNamespace) -> Dict[str, Any]:
    """Execute a single action and return result."""
    
    if not isinstance(action, dict):
        return {
            'action_num': action_num,
            'status': 'error',
            'error': 'Action must be a dictionary'
        }
    
    # Detect action type from playbook format
    action_type = None
    action_data = None
    
    # Check for playbook-style actions (command, click, keyboard, etc.)
    if 'command' in action:
        action_type = 'command'
        action_data = action['command']
    elif 'click' in action:
        action_type = 'click'
        action_data = action['click']
    elif 'keyboard' in action:
        action_type = 'keyboard'
        action_data = action['keyboard']
    elif 'idle' in action:
        action_type = 'idle'
        action_data = action['idle']
    elif 'screenshot' in action:
        action_type = 'screenshot'
        action_data = action['screenshot']
    elif 'type' in action:
        # Fallback to simple format
        action_type = action['type']
        action_data = action
    else:
        return {
            'action_num': action_num,
            'status': 'error', 
            'error': 'Unknown action format - no recognizable action type found'
        }
    
    description = action_data.get('description', f"{action_type} action") if isinstance(action_data, dict) else f"{action_type} action"
    log.info(f"[Action {action_num}] {description}")
    
    try:
        timeout = action_data.get('timeout', args.default_timeout) if isinstance(action_data, dict) else args.default_timeout
        
        if action_type == 'command':
            command = action_data.get('command') if isinstance(action_data, dict) else action_data
            if not command:
                raise ValueError("Command action requires 'command' field")
            
            result = await client.execute_shell(
                shell_command=command,
                cwd=action_data.get('cwd') if isinstance(action_data, dict) else None,
                timeout=timeout,
                shell=action_data.get('shell', True) if isinstance(action_data, dict) else True,
                env=action_data.get('env') if isinstance(action_data, dict) else None
            )
            
        elif action_type == 'screenshot':
            params = action_data if isinstance(action_data, dict) else {}
            result = await client.screenshot()
            
        elif action_type == 'click':
            # Handle both coordinate-based and target-based clicks
            if isinstance(action_data, dict):
                if 'x' in action_data and 'y' in action_data:
                    result = await client.click(action_data['x'], action_data['y'])
                else:
                    # For now, skip target-based clicks (would need MCP integration)
                    result = {"status": "skipped", "message": "Target-based clicks not yet implemented in WebSocket mode"}
            else:
                raise ValueError("Click action requires coordinate or target data")
            
        elif action_type == 'keyboard':
            if isinstance(action_data, dict):
                if 'combination' in action_data:
                    # Handle key combinations
                    combination = action_data['combination']
                    if isinstance(combination, list):
                        key = '+'.join(combination)
                    else:
                        key = str(combination)
                    result = await client.keyboard('hotkey', key)
                elif 'key' in action_data:
                    key_type = action_data.get('type', 'type')
                    result = await client.keyboard(key_type, action_data['key'])
                else:
                    raise ValueError("Keyboard action requires 'key' or 'combination' field")
            else:
                result = await client.keyboard('type', str(action_data))
            
        elif action_type == 'idle':
            duration = action_data.get('duration', 1.0) if isinstance(action_data, dict) else float(action_data)
            result = await client.idle(duration)
            
        elif action_type == 'get_status':
            result = await client.get_status()
            
        else:
            result = {"status": "skipped", "message": f"Action type '{action_type}' not supported in WebSocket mode"}
        
        # Add execution metadata
        return {
            'action_num': action_num,
            'action_type': action_type,
            'description': description,
            'status': 'success',
            'result': result
        }
        
    except WebSocketTimeoutError as e:
        log.error(f"[Action {action_num}] Timeout: {e}")
        return {
            'action_num': action_num,
            'action_type': action_type,
            'description': description,
            'status': 'timeout',
            'error': str(e)
        }
    except Exception as e:
        log.error(f"[Action {action_num}] Error: {e}")
        return {
            'action_num': action_num,
            'action_type': action_type,
            'description': description,
            'status': 'error',
            'error': str(e)
        }

def output_results(results: List[Dict[str, Any]], output_format: str):
    """Output results in the specified format."""
    
    if output_format == 'json':
        print(json.dumps(results, indent=2))
    elif output_format == 'yaml':
        print(yaml.dump(results, default_flow_style=False))
    elif output_format == 'summary':
        print(f"\nExecution Summary:")
        print(f"==================")
        total = len(results)
        success = len([r for r in results if r['status'] == 'success'])
        errors = len([r for r in results if r['status'] == 'error'])
        timeouts = len([r for r in results if r['status'] == 'timeout'])
        
        print(f"Total actions: {total}")
        print(f"Successful: {success}")
        print(f"Errors: {errors}")
        print(f"Timeouts: {timeouts}")
        print()
        
        for result in results:
            status_icon = "✓" if result['status'] == 'success' else "✗"
            action_type = result.get('action_type', 'unknown')
            description = result.get('description', f"{action_type} action")
            print(f"{status_icon} Action {result['action_num']} ({action_type}): {result['status']}")
            print(f"   Description: {description}")
            
            if result['status'] == 'success' and 'result' in result:
                print_detailed_result(result['result'], action_type)
            elif result['status'] != 'success':
                print(f"   Error: {result.get('error', 'Unknown error')}")
        
        if errors > 0 or timeouts > 0:
            sys.exit(1)
    else:
        # Default: simple text output with more detail
        for result in results:
            status_icon = "✓" if result['status'] == 'success' else "✗"
            action_type = result.get('action_type', 'unknown')
            description = result.get('description', f"{action_type} action")
            
            print(f"{status_icon} Action {result['action_num']} ({action_type}): {result['status']}")
            print(f"   {description}")
            
            if result['status'] == 'success' and 'result' in result:
                print_detailed_result(result['result'], action_type)
            elif result['status'] != 'success':
                print(f"   ❌ Error: {result.get('error', 'Unknown error')}")
            print()

def print_detailed_result(result: Dict[str, Any], action_type: str):
    """Print detailed result information based on action type."""
    if not isinstance(result, dict):
        print(f"   Result: {result}")
        return
    
    if action_type == 'command':
        stdout = result.get('stdout', '').strip()
        stderr = result.get('stderr', '').strip()
        returncode = result.get('returncode', 'unknown')
        
        print(f"   Return code: {returncode}")
        
        if stdout:
            print(f"   stdout: {stdout}")
        
        if stderr:
            print(f"   stderr: {stderr}")
    
    else:
        # For non-command actions, show basic result
        if 'status' in result:
            print(f"   Status: {result['status']}")
        if 'message' in result:
            print(f"   Message: {result['message']}")
        elif len(str(result)) > 100:
            print(f"   Result: {str(result)[:100]}...")
        else:
            print(f"   Result: {result}")

def create_example_action_file(file_path: Path):
    """Create an example action file in playbook format."""
    example = {
        'actions': [
            {
                'command': {
                    'name': 'Get VM Status',
                    'description': 'Check adarevm server status',
                    'command': 'echo "Checking VM status"',
                    'shell': True
                }
            },
            {
                'command': {
                    'name': 'List Directory',
                    'description': 'List files in current directory',
                    'command': 'dir',
                    'shell': True
                }
            },
            {
                'idle': {
                    'duration': 2.0,
                    'description': 'Wait 2 seconds'
                }
            },
            {
                'keyboard': {
                    'combination': ['ctrl', 'c'],
                    'description': 'Press Ctrl+C'
                }
            },
            {
                'screenshot': {
                    'description': 'Take a screenshot'
                }
            },
            {
                'click': {
                    'x': 100,
                    'y': 200,
                    'description': 'Click at coordinates (100, 200)'
                }
            }
        ]
    }
    
    with open(file_path, 'w') as f:
        yaml.dump(example, f, default_flow_style=False, sort_keys=False)
    
    print(f"Example playbook-format action file created: {file_path}")
    print("\nNow you can execute it with:")
    print(f"adare ws action {file_path} --host VM_IP")
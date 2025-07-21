from fastmcp import FastMCP, Image
import pyautogui
from io import BytesIO
import platform
import subprocess
import logging
import json
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional
import base64

# Set up logging
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
handler = logging.FileHandler('mcpserver.log')
handler.setLevel(logging.DEBUG)

mcp = FastMCP(name="adarevm", port=13108, host="localhost", debug=True)

# Global state for test management
testfunctions_dir: Optional[Path] = None
testset_instance: Optional[Any] = None
current_variables: Dict[str, Any] = {}


def __screenshot(x: int = None, y: int = None, width: int = None, height: int = None):
    """
    Take a screenshot and return the image data and offset in JSON-safe format.
    """
    import base64
    # Take screenshot (full or region)
    if x is not None and y is not None and width is not None and height is not None:
        screenshot = pyautogui.screenshot(region=(x, y, width, height))
    else:
        screenshot = pyautogui.screenshot()

    # Convert to bytes
    buffer = BytesIO()
    screenshot.save(buffer, format="PNG")
    img_bytes = buffer.getvalue()

    # Convert to base64
    img_base64 = base64.b64encode(img_bytes).decode("utf-8")

    # Return JSON-serializable dict
    return {
        "image": {
            "data": img_base64,
            "format": "png"
        },
        "offset": {
            "x": x if x is not None else 0,
            "y": y if y is not None else 0
        }
    }


@mcp.tool()
def screenshot():
    return __screenshot()


@mcp.tool()
def screenshot_window(window: str) -> list[Image]:
    screenshots = []
    if platform.system() == "Windows":
        pass
    elif platform.system() == "Linux":
        from adarevm.platforms.linux import get_windows_by_search_string
        windows = get_windows_by_search_string(window)
        if not windows:
            return []
        for i, win in enumerate(windows):
            log.debug(f"Taking screenshot of window {i}: {win.name} at {win.rect}")
            x, y, width, height = win.rect
            screenshot = __screenshot(x=x, y=y, width=width, height=height)
            screenshots.append(screenshot)
    else:
        raise NotImplementedError("Screenshot for this platform is not implemented yet.")
    return screenshots



@mcp.tool()
def click(x: int, y: int):
    """
    Simulate a mouse click at the specified coordinates.
    """
    pyautogui.click(x, y)
    return {"status": "success", "message": f"Clicked at ({x}, {y})"}


@mcp.tool()
def right_click(x: int, y: int):
    """
    Simulate a right mouse click at the specified coordinates.
    """
    pyautogui.rightClick(x, y)
    return {"status": "success", "message": f"Right clicked at ({x}, {y})"}


@mcp.tool()
def double_click(x: int, y: int):
    """
    Simulate a double mouse click at the specified coordinates.
    """
    pyautogui.doubleClick(x, y)
    return {"status": "success", "message": f"Double clicked at ({x}, {y})"}


@mcp.tool()
def drag(x1: int, y1: int, x2: int, y2: int):
    """
    Simulate a mouse drag from (x1, y1) to (x2, y2).
    """
    pyautogui.dragTo(x2, y2, duration=0.5)
    return {"status": "success", "message": f"Dragged from ({x1}, {y1}) to ({x2}, {y2})"}


@mcp.tool()
def keyboard(type: str, key: str):
    """
    Simulate a keyboard action.
    """
    if type == "press":
        pyautogui.press(key)
    elif type == "type":
        pyautogui.typewrite(key)
    elif type == "hotkey":
        pyautogui.hotkey(*key.split("+"))
    return {"status": "success", "message": f"Keyboard action {type} on {key}"}


@mcp.tool()
def scroll(direction: str, amount: int):
    """
    Simulate a scroll action.
    """
    if direction == "up":
        pyautogui.scroll(amount)
    elif direction == "down":
        pyautogui.scroll(-amount)
    return {"status": "success", "message": f"Scrolled {direction} by {amount}"}


@mcp.tool()
def goto(x: int, y: int):
    """
    Move the mouse to the specified coordinates.
    """
    pyautogui.moveTo(x, y)
    return {"status": "success", "message": f"Moved to ({x}, {y})"}


@mcp.tool()
def idle(duration: float):
    """
    Simulate an idle action for the specified duration.
    """
    pyautogui.sleep(duration)
    return {"status": "success", "message": f"Idle for {duration} seconds"}


# Test Management Functions

@mcp.tool()
def upload_testfunctions(testfunctions_data: str):
    """
    Upload testfunction files to the VM.
    
    Args:
        testfunctions_data: Base64 encoded zip file containing testfunctions
    
    Returns:
        Status of the upload operation
    """
    global testfunctions_dir
    
    try:
        # Decode the base64 data
        zip_data = base64.b64decode(testfunctions_data)
        
        # Create temporary directory for testfunctions
        testfunctions_dir = Path(tempfile.mkdtemp(prefix="adare_testfunctions_"))
        
        # Write zip file
        zip_path = testfunctions_dir / "testfunctions.zip"
        with open(zip_path, 'wb') as f:
            f.write(zip_data)
        
        # Extract zip file
        shutil.unpack_archive(zip_path, testfunctions_dir)
        zip_path.unlink()  # Remove zip file after extraction
        
        log.info(f"Testfunctions uploaded to {testfunctions_dir}")
        
        return {
            "status": "success", 
            "message": f"Testfunctions uploaded to {testfunctions_dir}",
            "path": str(testfunctions_dir)
        }
        
    except Exception as e:
        log.error(f"Error uploading testfunctions: {e}")
        return {"status": "error", "message": str(e)}


@mcp.tool()
def upload_testset(testset_yaml: str):
    """
    Upload testset YAML configuration.
    
    Args:
        testset_yaml: YAML content as string
    
    Returns:
        Status of the upload operation
    """
    global testset_instance, testfunctions_dir
    
    try:
        if not testfunctions_dir or not testfunctions_dir.exists():
            return {"status": "error", "message": "Testfunctions must be uploaded first"}
        
        # Write testset YAML file
        testset_path = testfunctions_dir / "testset.yml"
        with open(testset_path, 'w') as f:
            f.write(testset_yaml)
        
        # Import testset functionality (will need to handle imports carefully)
        try:
            # This would need to be adapted based on the actual import structure
            from adarevm.testset.testset import Testset
            
            async def dummy_log_func(message: str):
                log.info(f"Testset: {message}")
            
            # Create testset instance
            testset_instance = Testset(testfunctions_dir, testset_path, dummy_log_func)
            
            return {
                "status": "success",
                "message": f"Testset loaded with {len(testset_instance.tests)} tests",
                "tests": list(testset_instance.tests.keys())
            }
            
        except ImportError as e:
            return {"status": "error", "message": f"Failed to import testset modules: {e}"}
        
    except Exception as e:
        log.error(f"Error uploading testset: {e}")
        return {"status": "error", "message": str(e)}


@mcp.tool()
def set_variables(variables: str):
    """
    Set variables for test execution.
    
    Args:
        variables: JSON string containing variable key-value pairs
    
    Returns:
        Status of the operation
    """
    global current_variables
    
    try:
        new_variables = json.loads(variables)
        current_variables.update(new_variables)
        
        return {
            "status": "success", 
            "message": f"Set {len(new_variables)} variables",
            "variables": current_variables
        }
        
    except Exception as e:
        log.error(f"Error setting variables: {e}")
        return {"status": "error", "message": str(e)}


@mcp.tool()
def run_test(test_name: str):
    """
    Run a specific test by name.
    
    Args:
        test_name: Name of the test to run
    
    Returns:
        Test execution result
    """
    global testset_instance, current_variables
    
    try:
        if not testset_instance:
            return {"status": "error", "message": "No testset loaded. Upload testset first."}
        
        if test_name not in testset_instance.tests:
            available_tests = list(testset_instance.tests.keys())
            return {
                "status": "error", 
                "message": f"Test '{test_name}' not found. Available tests: {available_tests}"
            }
        
        # Execute the test
        testset_instance.test(test_name, current_variables)
        
        return {
            "status": "success", 
            "message": f"Test '{test_name}' executed successfully"
        }
        
    except Exception as e:
        log.error(f"Error running test {test_name}: {e}")
        return {"status": "error", "message": str(e)}


@mcp.tool()
def run_all_tests():
    """
    Run all available tests.
    
    Returns:
        Test execution results
    """
    global testset_instance, current_variables
    
    try:
        if not testset_instance:
            return {"status": "error", "message": "No testset loaded. Upload testset first."}
        
        # Execute all tests
        testset_instance.testall(current_variables)
        
        return {
            "status": "success", 
            "message": f"All {len(testset_instance.tests)} tests executed",
            "tests": list(testset_instance.tests.keys())
        }
        
    except Exception as e:
        log.error(f"Error running all tests: {e}")
        return {"status": "error", "message": str(e)}


@mcp.tool()
def list_tests():
    """
    List available tests.
    
    Returns:
        List of available test names
    """
    global testset_instance
    
    try:
        if not testset_instance:
            return {"status": "error", "message": "No testset loaded. Upload testset first."}
        
        return {
            "status": "success",
            "tests": list(testset_instance.tests.keys()),
            "count": len(testset_instance.tests)
        }
        
    except Exception as e:
        log.error(f"Error listing tests: {e}")
        return {"status": "error", "message": str(e)}


@mcp.tool()
def execute_command(command_name: str):
    """
    Execute a predefined command from the testset.
    
    Args:
        command_name: Name of the command to execute
    
    Returns:
        Command execution result
    """
    global testset_instance
    
    try:
        if not testset_instance:
            return {"status": "error", "message": "No testset loaded. Upload testset first."}
        
        # Execute the command
        testset_instance.execute_command(command_name)
        
        return {
            "status": "success", 
            "message": f"Command '{command_name}' executed successfully"
        }
        
    except Exception as e:
        log.error(f"Error executing command {command_name}: {e}")
        return {"status": "error", "message": str(e)}


@mcp.tool()
def get_status():
    """
    Get the current status of the test environment.
    
    Returns:
        Current status information
    """
    global testfunctions_dir, testset_instance, current_variables
    
    return {
        "testfunctions_uploaded": testfunctions_dir is not None and testfunctions_dir.exists(),
        "testfunctions_path": str(testfunctions_dir) if testfunctions_dir else None,
        "testset_loaded": testset_instance is not None,
        "available_tests": list(testset_instance.tests.keys()) if testset_instance else [],
        "variables_count": len(current_variables),
        "variables": current_variables
    }


def main():
    mcp.run(transport="streamable-http", host="0.0.0.0", port=13108, path="/mcp")

if __name__ == "__main__":
    main()

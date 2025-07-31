import asyncio
import base64
import json
from pathlib import Path
from fastmcp import Client
import cv2
import numpy as np


async def test_find_icon():
    """Simple test using FastMCP client that assumes MCP server is already running on localhost:13109."""
    
    # Test files directory
    test_files_dir = Path(__file__).parent / "files"
    icon_path = test_files_dir / "icon.png"
    screenshot_path = test_files_dir / "screenshot.png"
    
    # Check if test files exist
    if not icon_path.exists() or not screenshot_path.exists():
        print("SKIP: Test files (icon.png, screenshot.png) not found in tests/files directory")
        return
    
    # Read and encode files to base64
    with open(icon_path, "rb") as f:
        icon_base64 = base64.b64encode(f.read()).decode('utf-8')
    
    with open(screenshot_path, "rb") as f:
        screenshot_base64 = base64.b64encode(f.read()).decode('utf-8')
    
    try:
        async with Client("http://localhost:13109/mcp") as client:
            print("Connected to MCP server, calling find_icon tool...")
            
            result = await client.call_tool("find_icon", {
                "icon_base64": icon_base64,
                "screenshot_base64": screenshot_base64,
                "threshold": 0.6
            })
            
            # Parse the result - check both data and content
            if result.data is not None:
                response = result.data
            elif result.content and len(result.content) > 0:
                # Parse JSON from content text
                response = json.loads(result.content[0].text)
            else:
                print("FAIL: No data found in result")
                return
            
            print(f"Raw response: {json.dumps(response, indent=2)}")
            
            if "locations" in response:
                locations = response["locations"]
                print(f"SUCCESS: Found {len(locations)} icon matches")
                
                for i, location in enumerate(locations):
                    print(f"  Match {i+1}: x={location[0]}, y={location[1]}")
                
                # Create image with red dots at found locations
                if locations:
                    screenshot_img = cv2.imdecode(np.frombuffer(base64.b64decode(screenshot_base64), np.uint8), cv2.IMREAD_COLOR)
                    icon_img = cv2.imdecode(np.frombuffer(base64.b64decode(icon_base64), np.uint8), cv2.IMREAD_COLOR)
                    icon_height, icon_width = icon_img.shape[:2]
                    
                    result_img = screenshot_img.copy()
                    for x, y in locations:
                        # Convert to int if they're strings
                        x, y = int(x), int(y)
                        # Draw red dot at center of found icon
                        center_x = x + icon_width // 2
                        center_y = y + icon_height // 2
                        cv2.circle(result_img, (center_x, center_y), 10, (0, 0, 255), -1)  # Red circle
                    
                    # Save result
                    output_path = test_files_dir / "screenshot_with_red_dot.png"
                    cv2.imwrite(str(output_path), result_img)
                    print(f"Saved result with red dot to: {output_path}")
            
            if "error" in response:
                print(f"Error: {response['error']}")
    
    except Exception as e:
        print(f"FAIL: {e}")
        print("Make sure the server is running with: python -m adare_mcp_server.server")


if __name__ == "__main__":
    asyncio.run(test_find_icon())
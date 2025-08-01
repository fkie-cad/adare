import asyncio
import base64
import json
from pathlib import Path
from fastmcp import Client


async def test_find_text():
    """Test using FastMCP client to find 'Documents' text in screenshot2.png."""
    
    # Test files directory
    test_files_dir = Path(__file__).parent / "files"
    screenshot_path = test_files_dir / "screenshot2.png"
    
    # Check if test file exists
    if not screenshot_path.exists():
        print("SKIP: Test file (screenshot2.png) not found in tests/files directory")
        return
    
    # Read and encode file to base64
    with open(screenshot_path, "rb") as f:
        screenshot_base64 = base64.b64encode(f.read()).decode('utf-8')
    
    try:
        async with Client("http://localhost:13109/mcp") as client:
            print("Connected to MCP server, calling find_text tool...")
            
            result = await client.call_tool("find_text", {
                "text": "Documents",
                "screenshot_base64": screenshot_base64
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
                print(f"SUCCESS: Found {len(locations)} text matches for 'Documents'")
                
                for i, match in enumerate(locations):
                    text = match.get("text", "")
                    location = match.get("location", {})
                    x = location.get("x", 0)
                    y = location.get("y", 0)
                    print(f"  Match {i+1}: '{text}' at x={x}, y={y}")
            
            if "error" in response:
                print(f"Error: {response['error']}")
    
    except Exception as e:
        print(f"FAIL: {e}")
        print("Make sure the server is running with: python -m adare_mcp_server.server")


if __name__ == "__main__":
    asyncio.run(test_find_text())
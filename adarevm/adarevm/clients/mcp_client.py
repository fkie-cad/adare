from fastmcp import Client, Image
from fastmcp.resources import FileResource, TextResource, DirectoryResource
import asyncio
import base64
import json
import httpx

async def main():
    # Configure client with longer timeout for PaddleOCR operations
    timeout = httpx.Timeout(120.0)  # 2 minute timeout
    async with Client("http://localhost:13109/mcp", timeout=timeout) as client:
        # result = await client.call_tool("find_icon", {"icon": "mglass.png", "window": "nautilus"})
        # data = result[0].text
        # locations = json.loads(data)["locations"]
        # print("Icon locations:", locations)
        result = await client.call_tool("find_text", {"text": "Music", "window": "nautilus"})
        data = result[0].text
        locations = json.loads(data)["locations"]
        x = locations[0]['location']['x']
        y = locations[0]['location']['y']
        print("Icon locations:", locations)
    
    async with Client("http://localhost:13108/mcp") as client:
        result = await client.call_tool("click", {"x": x, "y": y})
        


if __name__ == "__main__":
    asyncio.run(main())











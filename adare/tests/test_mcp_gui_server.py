#!/usr/bin/env python3
"""
Test MCP GUI server find_text functionality with automatic server management.

This test starts the MCP GUI server, tests it, then stops it.
"""

import asyncio
import base64
import json
import pytest
import subprocess
import time
from pathlib import Path
from fastmcp import Client
import logging

# Setup logging for test visibility
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


class MCPServerTestManager:
    """Manager for starting/stopping MCP server during tests."""
    
    def __init__(self, port=13109):  # Use different port to avoid conflicts
        self.port = port
        self.process = None
        self.server_url = f"http://localhost:{port}/mcp"
    
    async def start_server(self):
        """Start MCP GUI server subprocess."""
        log.info(f"Starting MCP GUI server on port {self.port}...")
        
        # Find adare installation directory
        adare_dir = Path(__file__).parent.parent.parent
        
        # Start server process with custom port
        self.process = subprocess.Popen(
            ["poetry", "run", "python", "-m", "adare.mcp_gui", "--mode", "cv", "--port", str(self.port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Combine stderr into stdout
            text=True,
            cwd=str(adare_dir)
        )
        
        # Give it a moment to start
        await asyncio.sleep(2)
        
        # Check if process is still running
        if self.process.poll() is not None:
            # Process died, get output
            stdout, _ = self.process.communicate()
            log.error(f"MCP server process died immediately. Output:\n{stdout}")
            raise Exception(f"MCP server failed to start: {stdout}")
        
        # Wait for server to start
        await self._wait_for_server_ready()
        log.info("MCP GUI server started successfully")
    
    async def stop_server(self):
        """Stop MCP GUI server subprocess."""
        if self.process:
            log.info("Stopping MCP GUI server...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None
            log.info("MCP GUI server stopped")
    
    async def _wait_for_server_ready(self, max_attempts=20):
        """Wait for server to be ready."""
        import aiohttp
        
        for attempt in range(max_attempts):
            try:
                # Check the base server URL (without /mcp) for health
                base_url = f"http://localhost:{self.port}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(base_url, timeout=2) as response:
                        if response.status in [200, 404, 405]:  # 405 Method Not Allowed is also fine
                            log.info(f"MCP server responded with status {response.status}")
                            return True
            except Exception as e:
                log.debug(f"Attempt {attempt + 1}: {e}")
                if attempt < max_attempts - 1:
                    await asyncio.sleep(0.5)
        
        raise Exception(f"MCP server failed to start after {max_attempts} attempts")


@pytest.fixture(scope="module")
def mcp_server():
    """Pytest fixture to manage MCP server lifecycle."""
    manager = MCPServerTestManager()
    
    # Start server synchronously for fixture
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(manager.start_server())
        yield manager
    finally:
        if not loop.is_closed():
            loop.run_until_complete(manager.stop_server())
            loop.close()


@pytest.mark.asyncio
async def test_mcp_server_connection(mcp_server):
    """Test basic MCP server connection and tool listing."""
    async with Client(mcp_server.server_url) as client:
        tools = await client.list_tools()
        tool_names = [tool.name for tool in tools]
        
        # Verify expected tools are available
        assert "find_text" in tool_names
        assert "find_icon" in tool_names
        log.info(f"✅ Available tools: {tool_names}")


@pytest.mark.asyncio
async def test_mcp_find_text_with_image(mcp_server):
    """Test find_text tool with a sample image."""
    
    # Use existing test image from tests/files
    test_image_path = Path(__file__).parent / "files/screenshot.png"
    
    if not test_image_path.exists():
        pytest.skip(f"Test image not found: {test_image_path}")
    
    # Read and encode the image
    with open(test_image_path, "rb") as f:
        image_data = f.read()
        screenshot_base64 = base64.b64encode(image_data).decode('utf-8')
    
    log.info(f"🖼️  Testing with image: {test_image_path}")
    log.info(f"📊 Image size: {len(image_data)} bytes")
    
    async with Client(mcp_server.server_url) as client:
        # Test find_text with common text that might be in the image
        test_texts = ["Documents"]
        found_any_text = False
        
        for text in test_texts:
            log.info(f"🔍 Searching for text: '{text}'")
            
            result = await client.call_tool("find_text", {
                "text": text,
                "screenshot_base64": screenshot_base64,
                "offset_x": 0,
                "offset_y": 0
            })
            
            # Parse response
            data = result[0].text
            locations_data = json.loads(data)
            locations = locations_data.get("locations", [])
            
            if locations:
                found_any_text = True
                log.info(f"✅ Found '{text}' at {len(locations)} location(s):")
                for i, location in enumerate(locations):
                    found_text = location["text"]
                    x = location["location"]["x"]
                    y = location["location"]["y"]
                    log.info(f"   {i+1}. '{found_text}' at ({x}, {y})")
                    
                    # Verify location data structure
                    assert isinstance(x, int)
                    assert isinstance(y, int)
                    assert isinstance(found_text, str)
                    assert len(found_text) > 0
            else:
                log.info(f"❌ Text '{text}' not found")
        
        # We expect to find at least some text in the image
        assert found_any_text, "Expected to find at least some text in the test image"


@pytest.mark.asyncio
async def test_mcp_find_text_empty_result(mcp_server):
    """Test find_text with text that definitely doesn't exist."""
    
    # Use existing test image from tests/files
    test_image_path = Path(__file__).parent / "files/screenshot.png"
    
    if not test_image_path.exists():
        pytest.skip(f"Test image not found: {test_image_path}")
    
    # Read and encode the image
    with open(test_image_path, "rb") as f:
        image_data = f.read()
        screenshot_base64 = base64.b64encode(image_data).decode('utf-8')
    
    async with Client(mcp_server.server_url) as client:
        # Search for text that definitely doesn't exist
        result = await client.call_tool("find_text", {
            "text": "ThisTextDefinitelyDoesNotExistInTheImage123",
            "screenshot_base64": screenshot_base64,
            "offset_x": 0,
            "offset_y": 0
        })
        
        # Parse response
        data = result[0].text
        locations_data = json.loads(data)
        locations = locations_data.get("locations", [])
        
        # Should return empty list
        assert locations == []
        log.info("✅ Correctly returned empty result for non-existent text")


if __name__ == "__main__":
    # Run with pytest
    pytest.main([__file__, "-v", "-s"])
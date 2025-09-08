import asyncio
import base64
import json
import logging
import subprocess
import time
import signal
import os
from pathlib import Path
from types import SimpleNamespace

import click
from fastmcp import Client

log = logging.getLogger(__name__)


class MCPServerManager:
    """Manages the MCP server lifecycle."""
    
    def __init__(self, host='localhost', port=13109):
        self.host = host
        self.port = port
        self.process = None
        self.server_url = f"http://{host}:{port}/mcp"
    
    async def start_server(self):
        """Start the MCP server if not already running."""
        # Check if server is already running
        if await self._is_server_running():
            print(f"✅ MCP server already running at {self.server_url}")
            return True
        
        print(f"🚀 Starting MCP server at {self.server_url}")
        
        try:
            # Start the server process
            self.process = subprocess.Popen([
                'adare-mcp-server', 
                '--host', self.host, 
                '--port', str(self.port)
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            
            # Wait for server to start
            for attempt in range(30):  # 30 second timeout
                await asyncio.sleep(1)
                if await self._is_server_running():
                    print(f"✅ MCP server started successfully")
                    return True
                print(f"⏳ Waiting for server to start... ({attempt + 1}/30)")
            
            print("❌ Server failed to start within 30 seconds")
            self.stop_server()
            return False
            
        except FileNotFoundError:
            print("❌ adare-mcp-server command not found. Make sure adare-mcp-server package is installed.")
            return False
        except Exception as e:
            print(f"❌ Failed to start server: {e}")
            return False
    
    async def _is_server_running(self):
        """Check if the MCP server is running."""
        try:
            async with Client(self.server_url) as client:
                # Try to list tools to verify server is responding
                return True
        except:
            return False
    
    def stop_server(self):
        """Stop the MCP server."""
        if self.process:
            print("🛑 Stopping MCP server...")
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            self.process = None
            print("✅ MCP server stopped")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.stop_server()


async def exec_mcp_test_icon(args):
    """Test MCP server icon finding functionality."""
    
    # Check that required paths are provided
    if not args.icon_path:
        print("❌ Icon file path is required. Use --icon option.")
        return
        
    if not args.screenshot_path:
        print("❌ Screenshot file path is required. Use --screenshot option.")
        return
    
    icon_path = Path(args.icon_path)
    screenshot_path = Path(args.screenshot_path)
    
    # Check if files exist
    if not icon_path.exists():
        print(f"❌ Icon file not found: {icon_path}")
        return
        
    if not screenshot_path.exists():
        print(f"❌ Screenshot file not found: {screenshot_path}")
        return
    
    # Read and encode files
    try:
        with open(icon_path, "rb") as f:
            icon_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        with open(screenshot_path, "rb") as f:
            screenshot_base64 = base64.b64encode(f.read()).decode('utf-8')
            
        print(f"📁 Using icon: {icon_path}")
        print(f"📁 Using screenshot: {screenshot_path}")
        
    except Exception as e:
        print(f"❌ Error reading files: {e}")
        return
    
    # Start MCP server for this command
    host = getattr(args, 'host', 'localhost')
    port = getattr(args, 'port', 13109)
    threshold = getattr(args, 'threshold', 0.6)
    
    async with MCPServerManager(host, port) as server_manager:
        # Start the server 
        if not await server_manager.start_server():
            return
        
        try:
            async with Client(server_manager.server_url) as client:
                print("✅ Connected to MCP server")
                print(f"🔍 Finding icon with threshold: {threshold}")
                
                result = await client.call_tool("find_icon", {
                    "icon_base64": icon_base64,
                    "screenshot_base64": screenshot_base64,
                    "threshold": threshold
                })
                
                # Parse result
                if result.data is not None:
                    response = result.data
                elif result.content and len(result.content) > 0:
                    response = json.loads(result.content[0].text)
                else:
                    print("❌ No data found in result")
                    return
                
                # Display results
                if "error" in response:
                    print(f"❌ Error: {response['error']}")
                    return
                    
                if "locations" in response:
                    locations = response["locations"]
                    similarities = response.get("similarities", [])
                    
                    # Debug: check what we got
                    print(f"🔍 Debug - Got {len(similarities)} similarities: {similarities[:5]}")  # Show first 5
                    
                    if locations:
                        print(f"✅ Found {len(locations)} icon matches:")
                        for i, location in enumerate(locations):
                            if isinstance(location, dict):
                                x = int(location.get("x", location.get("center_x", 0)))
                                y = int(location.get("y", location.get("center_y", 0)))
                            elif isinstance(location, (list, tuple)) and len(location) >= 2:
                                x, y = int(location[0]), int(location[1])
                            else:
                                x, y = 0, 0
                            
                            # Get similarity from separate array
                            similarity = similarities[i] if i < len(similarities) else "N/A"
                            if isinstance(similarity, float):
                                similarity = f"{similarity:.3f}"
                            
                            print(f"   Match {i+1}: x={x}, y={y}, similarity={similarity}")
                        
                        # Create marked image if output path provided
                        if hasattr(args, 'output_path') and args.output_path:
                            try:
                                # Use Pillow instead of OpenCV to avoid segfaults
                                from PIL import Image, ImageDraw
                                import io
                                
                                # Load images
                                screenshot_img = Image.open(io.BytesIO(base64.b64decode(screenshot_base64)))
                                icon_img = Image.open(io.BytesIO(base64.b64decode(icon_base64)))
                                icon_width, icon_height = icon_img.size
                                
                                # Create result image copy
                                result_img = screenshot_img.copy()
                                draw = ImageDraw.Draw(result_img)
                                
                                # Calculate min/max similarity for better color scaling
                                valid_similarities = []
                                for s in similarities:
                                    try:
                                        float_val = float(s)
                                        valid_similarities.append(float_val)
                                    except (ValueError, TypeError):
                                        pass
                                if valid_similarities:
                                    min_sim = min(valid_similarities)
                                    max_sim = max(valid_similarities)
                                    sim_range = max_sim - min_sim
                                else:
                                    min_sim, max_sim, sim_range = 0, 1, 1
                                
                                def similarity_to_color(similarity):
                                    """Convert similarity score to color gradient using actual min/max range."""
                                    try:
                                        float_sim = float(similarity)
                                    except (ValueError, TypeError):
                                        return "purple"  # Default color for unknown similarity
                                    
                                    # Scale similarity to 0-1 range based on actual min/max
                                    if sim_range > 0:
                                        normalized_sim = (float_sim - min_sim) / sim_range
                                    else:
                                        normalized_sim = 0.5  # If all similarities are the same
                                    
                                    # Clamp to 0-1 range
                                    normalized_sim = max(0.0, min(1.0, normalized_sim))
                                    
                                    # Create gradient from red (0) to yellow (0.5) to green (1)
                                    if normalized_sim < 0.5:
                                        # Red to yellow gradient
                                        red = 255
                                        green = int(255 * (normalized_sim * 2))
                                        blue = 0
                                    else:
                                        # Yellow to green gradient
                                        red = int(255 * (2 - normalized_sim * 2))
                                        green = 255
                                        blue = 0
                                    
                                    return f"#{red:02x}{green:02x}{blue:02x}"
                                
                                for i, location in enumerate(locations):
                                    # Extract coordinates based on format
                                    if isinstance(location, dict):
                                        x = int(location.get("x", location.get("center_x", 0)))
                                        y = int(location.get("y", location.get("center_y", 0)))
                                    elif isinstance(location, (list, tuple)) and len(location) >= 2:
                                        x, y = int(location[0]), int(location[1])
                                    else:
                                        continue
                                    
                                    # Get similarity for color coding
                                    similarity = similarities[i] if i < len(similarities) else None
                                    color = similarity_to_color(similarity)
                                    
                                    # Draw colored circle at center of found icon
                                    center_x = x + icon_width // 2
                                    center_y = y + icon_height // 2
                                    draw.ellipse([center_x-8, center_y-8, center_x+8, center_y+8], fill=color)
                                    
                                    # Draw colored rectangle around the match
                                    draw.rectangle([x, y, x + icon_width, y + icon_height], outline=color, width=3)
                                    
                                    # Add similarity text near the match
                                    try:
                                        sim_text = f"{float(similarity):.2f}"
                                        text_x = x + icon_width + 5
                                        text_y = y
                                        draw.text([text_x, text_y], sim_text, fill=color)
                                    except (ValueError, TypeError):
                                        pass  # Skip text if similarity can't be converted
                                
                                # Save result
                                output_path = Path(args.output_path)
                                result_img.save(str(output_path))
                                print(f"💾 Saved marked image to: {output_path}")
                                if valid_similarities:
                                    print(f"🎨 Color coding scaled to range: {min_sim:.3f} (red) → {max_sim:.3f} (green)")
                                else:
                                    print(f"🎨 Color coding: Red=low similarity, Yellow=medium, Green=high similarity")
                                
                            except Exception as e:
                                print(f"⚠️  Could not save marked image: {e}")
                    else:
                        print("ℹ️  No icon matches found")
                else:
                    print("❌ Unexpected response format")
                    
        except ConnectionError:
            print(f"❌ Could not connect to MCP server")
        except Exception as e:
            print(f"❌ Error testing MCP server: {e}")


async def exec_mcp_get_all_text(args):
    """Get all detected text from screenshot using MCP server."""
    
    # Check that required path is provided
    if not args.screenshot_path:
        print("❌ Screenshot file path is required. Use --screenshot option.")
        return
    
    screenshot_path = Path(args.screenshot_path)
    
    # Check if file exists
    if not screenshot_path.exists():
        print(f"❌ Screenshot file not found: {screenshot_path}")
        return
    
    # Read and encode file
    try:
        with open(screenshot_path, "rb") as f:
            screenshot_base64 = base64.b64encode(f.read()).decode('utf-8')
            
        print(f"📁 Using screenshot: {screenshot_path}")
        
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return
    
    # Start MCP server for this command
    host = getattr(args, 'host', 'localhost')
    port = getattr(args, 'port', 13109)
    format_type = getattr(args, 'format', 'json')
    
    async with MCPServerManager(host, port) as server_manager:
        # Start the server
        if not await server_manager.start_server():
            return
        
        try:
            async with Client(server_manager.server_url) as client:
                print("✅ Connected to MCP server")
                print(f"🔍 Getting all detected text (format: {format_type})")
                
                result = await client.call_tool("get_all_text", {
                    "screenshot_base64": screenshot_base64,
                    "format": format_type
                })
                
                # Parse result
                if result.data is not None:
                    response = result.data
                elif result.content and len(result.content) > 0:
                    response = json.loads(result.content[0].text)
                else:
                    print("❌ No data found in result")
                    return
                
                # Display results
                if "error" in response:
                    print(f"❌ Error: {response['error']}")
                    return
                
                if format_type.lower() == "csv" and "data" in response:
                    print("📊 All detected text (CSV format):")
                    print(response["data"])
                elif "all_text" in response:
                    all_text = response["all_text"]
                    if all_text:
                        print(f"✅ Found {len(all_text)} text detections:")
                        for i, detection in enumerate(all_text):
                            text = detection.get("text", "")
                            x = detection.get("x", 0)
                            y = detection.get("y", 0)
                            confidence = detection.get("confidence", 0)
                            print(f"   {i+1}: '{text}' at x={x}, y={y} (confidence: {confidence:.3f})")
                    else:
                        print("ℹ️  No text detected")
                else:
                    print("❌ Unexpected response format")
                    
        except ConnectionError:
            print(f"❌ Could not connect to MCP server")
        except Exception as e:
            print(f"❌ Error testing MCP server: {e}")


async def exec_mcp_test_text(args):
    """Test MCP server text finding functionality."""
    
    # Check that required path is provided
    if not args.screenshot_path:
        print("❌ Screenshot file path is required. Use --screenshot option.")
        return
    
    screenshot_path = Path(args.screenshot_path)
    
    # Check if file exists
    if not screenshot_path.exists():
        print(f"❌ Screenshot file not found: {screenshot_path}")
        return
    
    # Read and encode file
    try:
        with open(screenshot_path, "rb") as f:
            screenshot_base64 = base64.b64encode(f.read()).decode('utf-8')
            
        print(f"📁 Using screenshot: {screenshot_path}")
        
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return
    
    # Start MCP server for this command
    host = getattr(args, 'host', 'localhost')
    port = getattr(args, 'port', 13109)
    text = args.text
    format_type = getattr(args, 'format', 'json')
    
    async with MCPServerManager(host, port) as server_manager:
        # Start the server
        if not await server_manager.start_server():
            return
        
        try:
            async with Client(server_manager.server_url) as client:
                print("✅ Connected to MCP server")
                print(f"🔍 Finding text: '{text}' (format: {format_type})")
                
                result = await client.call_tool("find_text", {
                    "text": text,
                    "screenshot_base64": screenshot_base64,
                    "format": format_type
                })
                
                # Parse result
                if result.data is not None:
                    response = result.data
                elif result.content and len(result.content) > 0:
                    response = json.loads(result.content[0].text)
                else:
                    print("❌ No data found in result")
                    return
                
                # Display results
                if "error" in response:
                    print(f"❌ Error: {response['error']}")
                    return
                
                if format_type.lower() == "csv" and "data" in response:
                    print("📊 Text search results (CSV format):")
                    print(response["data"])
                elif "locations" in response:
                    locations = response["locations"]
                    if locations:
                        print(f"✅ Found {len(locations)} text matches:")
                        for i, match in enumerate(locations):
                            found_text = match.get("text", "")
                            location = match.get("location", {})
                            x = location.get("x", 0)
                            y = location.get("y", 0)
                            print(f"   Match {i+1}: '{found_text}' at x={x}, y={y}")
                    else:
                        print("ℹ️  No text matches found")
                else:
                    print("❌ Unexpected response format")
                    
        except ConnectionError:
            print(f"❌ Could not connect to MCP server")
        except Exception as e:
            print(f"❌ Error testing MCP server: {e}")


async def exec_mcp_start_server(args):
    """Start the MCP server and keep it running."""
    host = getattr(args, 'host', 'localhost')
    port = getattr(args, 'port', 13109)
    
    server_manager = MCPServerManager(host, port)
    
    if await server_manager.start_server():
        print(f"🎯 MCP server running at {server_manager.server_url}")
        print("Press Ctrl+C to stop the server...")
        
        try:
            # Keep the server running until interrupted
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n⚠️  Received interrupt signal")
        finally:
            server_manager.stop_server()
    else:
        print("❌ Failed to start MCP server")
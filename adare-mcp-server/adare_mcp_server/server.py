from fastmcp import FastMCP
import base64
import click
import logging
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

mcp = FastMCP(name="adare-mcp-server")


def find_icon_locations(screenshot_bytes: bytes, icon_bytes: bytes, threshold: float = 0.8):
    import cv2
    import numpy as np
    # Convert bytes to numpy arrays
    screenshot_array = np.frombuffer(screenshot_bytes, np.uint8)
    icon_array = np.frombuffer(icon_bytes, np.uint8)
    # Decode images
    screenshot_img = cv2.imdecode(screenshot_array, cv2.IMREAD_COLOR)
    icon_img = cv2.imdecode(icon_array, cv2.IMREAD_COLOR)
    # Template matching
    result = cv2.matchTemplate(screenshot_img, icon_img, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= threshold)
    points = list(zip(locations[1], locations[0]))  # (x, y)
    return points


@mcp.tool()
async def find_icon(icon_base64: str, screenshot_base64: str, offset_x: int = 0, offset_y: int = 0, threshold: float = 0.6):
    """Find icon locations in provided screenshot data using base64 encoded icon."""
    try:
        log.info(f"Starting icon search with base64 icon data")
        screenshot_bytes = base64.b64decode(screenshot_base64)
        icon_bytes = base64.b64decode(icon_base64)
        locations = find_icon_locations(screenshot_bytes, icon_bytes, threshold=threshold)
        locations = [(x + offset_x, y + offset_y) for x, y in locations]
        log.info(f"Found {len(locations)} icon matches")
        return {"locations": locations}
    except Exception as e:
        log.error(f"Icon search failed: {e}")
        return {
            "error": f"Icon search failed: {str(e)}", 
            "locations": []
        }


def _run_paddle_ocr(screenshot_path: str):
    """Run PaddleOCR in a separate thread to avoid blocking."""
    from paddleocr import PaddleOCR
    
    try:
        log.info("Initializing PaddleOCR...")
        ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)
        
        log.info("Running OCR prediction...")
        result = ocr.predict(input=screenshot_path)[0]
        
        log.info("OCR prediction completed")
        return result
    except Exception as e:
        log.error(f"OCR failed: {str(e)}")
        raise


@mcp.tool()
async def find_text(text: str, screenshot_base64: str, offset_x: int = 0, offset_y: int = 0):
    """Find text locations in provided screenshot data."""
    log.info(f"Starting text search for: '{text}'")
    
    try:
        screenshot_bytes = base64.b64decode(screenshot_base64)
        # save bytes in a temporary file
        screenshot_path = "screenshot.png"
        with open(screenshot_path, "wb") as f:
            f.write(screenshot_bytes)
        
        # Run PaddleOCR in thread pool
        executor = ThreadPoolExecutor(max_workers=1)
        
        try:
            log.info("Running PaddleOCR...")
            
            # Start the OCR task
            result = await asyncio.get_event_loop().run_in_executor(
                executor, _run_paddle_ocr, screenshot_path
            )
            
            log.info("PaddleOCR completed successfully")
            
        except Exception as e:
            log.error(f"PaddleOCR failed: {e}")
            return {
                "error": f"OCR processing failed: {str(e)}", 
                "locations": []
            }
        finally:
            executor.shutdown(wait=True)
            
    except Exception as e:
        log.error(f"Text search failed: {e}")
        return {
            "error": f"Text search failed: {str(e)}", 
            "locations": []
        }
    
    # find all indices in rec_texts that contain the text
    locations = []
    for i, (text_rec, box) in enumerate(zip(result['rec_texts'], result['rec_boxes'])):
        if text.lower() in text_rec.lower():
            x, y, x2, y2 = box
            center_x = int((x + x2) // 2) + offset_x
            center_y = int((y + y2) // 2) + offset_y
            locations.append({
                "text": text_rec,
                "location": {
                    "x": center_x,
                    "y": center_y,
                }
            })
    
    log.info(f"Found {len(locations)} text matches")
    return {
        "locations": locations
    }


def create_server():
    """Create the FastMCP server instance."""
    return mcp


@click.command()
@click.option('--port', type=int, default=13109, help='Port to run the MCP server on.')
@click.option('--host', type=str, default='localhost', help='Host to bind the server to.')
@click.option('--debug', is_flag=True, help='Enable debug logging.')
def main(port, host, debug):
    """Start the Adare MCP server."""
    
    # Configure logging
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    log.info(f"Starting Adare MCP server on {host}:{port}")
    
    try:
        # Run FastMCP server
        mcp.run(
            transport="streamable-http", 
            host=host, 
            port=port, 
            path="/mcp"
        )
    except Exception as e:
        log.error(f"MCP server failed to start: {e}")
        raise


if __name__ == "__main__":
    main()
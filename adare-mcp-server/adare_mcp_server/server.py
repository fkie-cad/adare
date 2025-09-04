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
    
    # Get dimensions
    icon_h, icon_w = icon_img.shape[:2]
    screenshot_h, screenshot_w = screenshot_img.shape[:2]
    
    # Template matching
    result = cv2.matchTemplate(screenshot_img, icon_img, cv2.TM_CCOEFF_NORMED)
    
    # Find locations above threshold
    locations = np.where(result >= threshold)
    points = list(zip(locations[1], locations[0]))  # (x, y)
    
    # Filter points so icon is completely within image bounds
    valid_points = []
    valid_similarities = []
    
    for x, y in points:
        # Check if the full icon would fit completely within bounds
        if x >= 0 and y >= 0 and x + icon_w <= screenshot_w and y + icon_h <= screenshot_h:
            # Return center coordinates instead of top-left corner
            center_x = x + icon_w // 2
            center_y = y + icon_h // 2
            valid_points.append((center_x, center_y))
            valid_similarities.append(float(result[y, x]))
    
    return valid_points, valid_similarities


@mcp.tool()
async def find_icon(icon_base64: str, screenshot_base64: str, offset_x: int = 0, offset_y: int = 0, threshold: float = 0.5, max_results: int = 50):
    """Find icon locations in provided screenshot data using base64 encoded icon."""
    try:
        log.info(f"Starting icon search with base64 icon data")
        screenshot_bytes = base64.b64decode(screenshot_base64)
        icon_bytes = base64.b64decode(icon_base64)
        locations, similarities = find_icon_locations(screenshot_bytes, icon_bytes, threshold=threshold)
        locations = [(x + offset_x, y + offset_y) for x, y in locations]

        if max_results:
            # sort by similarity and limit results
            sorted_results = sorted(zip(locations, similarities), key=lambda item: item[1],
                                    reverse=True)[:max_results]
            locations, similarities = zip(*sorted_results) if sorted_results else ([], [])

        log.info(f"Found {len(locations)} icon matches")
        return {
            "locations": locations,
            "similarities": similarities
        }
    except Exception as e:
        log.error(f"Icon search failed: {e}")
        return {
            "error": f"Icon search failed: {str(e)}", 
            "locations": [],
            "similarities": []
        }


def _run_paddle_ocr(screenshot_bytes: bytes):
    """Run PaddleOCR in a separate thread to avoid blocking."""
    from paddleocr import PaddleOCR
    import cv2
    import numpy as np
    
    try:
        log.info("Initializing PaddleOCR...")
        ocr = PaddleOCR(
            use_doc_orientation_classify=False, 
            use_doc_unwarping=False, 
            use_textline_orientation=False
        )
        
        log.info("Converting image bytes to numpy array...")
        # Convert bytes to numpy array
        nparr = np.frombuffer(screenshot_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        log.info("Running OCR prediction...")
        result = ocr.ocr(img)[0]
        
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
        
        # Run PaddleOCR in thread pool
        executor = ThreadPoolExecutor(max_workers=1)
        
        try:
            log.info("Running PaddleOCR...")
            
            # Start the OCR task with image bytes directly
            result = await asyncio.get_event_loop().run_in_executor(
                executor, _run_paddle_ocr, screenshot_bytes
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
    
    # find all detections that contain the text
    locations = []
    confidences = []
    for detection in result:
        box, (text_rec, confidence) = detection
        if text.lower() in text_rec.lower():
            # box is a list of 4 corner points [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            # Calculate center from bounding box
            x_coords = [point[0] for point in box]
            y_coords = [point[1] for point in box]
            center_x = int(sum(x_coords) / len(x_coords)) + offset_x
            center_y = int(sum(y_coords) / len(y_coords)) + offset_y
            locations.append({
                "text": text_rec,
                "location": {
                    "x": center_x,
                    "y": center_y,
                }
            })
            confidences.append(float(confidence))
    
    log.info(f"Found {len(locations)} text matches")
    return {
        "locations": locations,
        "confidences": confidences
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
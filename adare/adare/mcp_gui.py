from fastmcp import FastMCP, Image, Client
import base64
from pathlib import Path
import click
import logging
import json
log = logging.getLogger(__name__)

mcp = FastMCP(name="adaregui", port=13109, host="localhost", debug=True)

MODE = "cv"  # Default mode, can be overridden by command line argument
ICON_DIR = Path("/home/miq/Documents/test/icon/") # Directory where icons are stored
OMNIPARSER_API = "http://localhost:13201/omniparser"  # Example API endpoint for omniparser mod

async def screenshot(window: str = None):
    async with Client("http://localhost:13108/mcp") as client:
        if window:
            data = await client.call_tool("screenshot_window", {"window": window})
            data = json.loads(data[0].text)
            if len(data) == 0:
                raise None
            screenshot = data[0]
            if len(data) > 1:
                log.warning(f"Warning: Multiple screenshots found for window '{window}'. Using the first one.")
        else:
            data = await client.call_tool("screenshot") 
            data = json.loads(data[0].text)
            screenshot = json.loads(data[0].text)
        image_bytes = base64.b64decode(screenshot["image"]["data"])
        return image_bytes, screenshot["offset"]


def get_icon(name: str):
    """
    Retrieve an icon by its hash from the local directory.
    """
    icon_path = ICON_DIR / name
    print(f"Looking for icon: {icon_path}")
    if not icon_path.exists():
        raise FileNotFoundError(f"Icon '{name}' not found in {ICON_DIR}")
    with open(icon_path, "rb") as f:
        return f.read()
    

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
async def find_icon(icon: str, window: str = None):
    screenshot_bytes, offset = await screenshot(window=window)
    icon_bytes = get_icon(icon)
    locations = find_icon_locations(screenshot_bytes, icon_bytes, 0.8)
    locations = [(x + offset['x'], y + offset['y']) for x, y in locations]
    return {"locations": locations}


@mcp.tool()
async def find_text(text: str, window: str = None):
    from paddleocr import PaddleOCR
    ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)
    screenshot_bytes, offset = await screenshot(window=window)
    # save bytes in a temporary file
    with open("screenshot.png", "wb") as f:
        f.write(screenshot_bytes)
    result = ocr.predict(input="screenshot.png")[0]
    # find all indices in rec_texts that contain the text
    locations = []
    for i, (text_rec, box) in enumerate(zip(result['rec_texts'], result['rec_boxes'])):
        if text.lower() in text_rec.lower():
            x, y, x2, y2 = box
            center_x = int((x + x2) // 2) + offset['x']
            center_y = int((y + y2) // 2) + offset['y']
            locations.append({
                "text": text_rec,
                "location": {
                    "x": center_x,
                    "y": center_y,
                }
            })
    return {"locations": locations}

        

@click.command()
@click.option('--mode', type=click.Choice(['cv', 'omniparser']), default='cv', help='Mode to run the MCP server in.')
@click.option('--icon-dir', type=click.Path(exists=True), default='/home/miq/Documents/test/icon/', help='Directory where icons are stored.')
def main(mode, icon_dir):
    global MODE, ICON_DIR
    MODE = mode
    ICON_DIR = Path(icon_dir)
    mcp.run(transport="streamable-http", host="0.0.0.0", port=13109, path="/mcp")


if __name__ == "__main__":
    main()


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










# def detect_top_bar_dynamic(image_path, max_scan_height_ratio=0.25, color_change_thresh=15, debug=False, save_path="top_bar_detected.png"):
#     import cv2
#     import numpy as np
#     import matplotlib.pyplot as plt
#     image = cv2.imread(image_path)
#     if image is None:
#         raise FileNotFoundError(f"Image not found: {image_path}")

#     height, width = image.shape[:2]
#     scan_height = int(height * 0.25)
#     gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
#     roi = gray[:scan_height, :]

#     # Use Sobel Y to detect horizontal changes
#     sobel_y = cv2.Sobel(roi, cv2.CV_64F, 0, 1, ksize=3)
#     abs_sobel = np.abs(sobel_y)
#     row_strengths = abs_sobel.mean(axis=1)

#     # Dynamic threshold based on image stats
#     mean_strength = np.mean(row_strengths)
#     std_strength = np.std(row_strengths)
#     threshold = mean_strength + 1.5 * std_strength

#     # Find first row where edge strength exceeds threshold
#     for y in range(10, scan_height):  # skip first 10 rows (some noise)
#         if row_strengths[y] > threshold:
#             bar_height = max(y, 30)  # ensure minimum height
#             if debug:
#                 debug_img = cv2.cvtColor(image.copy(), cv2.COLOR_BGR2RGB)
#                 cv2.rectangle(debug_img, (0, 0), (width, bar_height), (0, 255, 0), 2)
#                 plt.imsave(save_path, debug_img)
#             return (0, 0, width, bar_height)

#     return None

        
# def show_edges(image_path):
#     import cv2
#     import matplotlib.pyplot as plt
#     import numpy as np
#     # Load image
#     image = cv2.imread(image_path)
#     gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
#     gray = cv2.equalizeHist(gray)

#     # Edge detection (enhance subtle lines)
#     edges = cv2.Canny(gray, 50, 150, apertureSize=3)

#     # Probabilistic Hough Transform
#     lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=50, maxLineGap=5)

#     print("Detected horizontal/vertical lines:")
#     if lines is not None:
#         for i, line in enumerate(lines):
#             x1, y1, x2, y2 = line[0]
#             dx = x2 - x1
#             dy = y2 - y1

#             angle = np.arctan2(dy, dx) * 180.0 / np.pi
#             angle = abs(angle)

#             # Keep only near-horizontal or near-vertical lines
#             if angle < 5 or abs(angle - 90) < 5:
#                 print(f"[{i}] Line: ({x1}, {y1}) → ({x2}, {y2}), angle={angle:.1f}")
#                 cv2.line(image, (x1, y1), (x2, y2), (0, 255, 0), 2)

#     # Save outputs
#     cv2.imwrite("output_hough_lines.png", image)
#     cv2.imwrite("output_edges.png", edges)
#     print("Saved 'output_hough_lines.png' and 'output_edges.png'")
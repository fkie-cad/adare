from fastmcp import FastMCP
import base64
import click
import logging
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

mcp = FastMCP(name="adare-mcp-server")


def find_icon_locations_sift(screenshot_bytes: bytes, icon_bytes: bytes, min_matches: int = 10, ratio_threshold: float = 0.75):
    """Find icon locations using SIFT feature matching - scale invariant."""
    import cv2
    import numpy as np
    
    log.info(f"CLAUDE: SIFT detection starting with min_matches={min_matches}, ratio_threshold={ratio_threshold}")
    
    # Decode images
    screenshot_array = np.frombuffer(screenshot_bytes, np.uint8)
    icon_array = np.frombuffer(icon_bytes, np.uint8)
    screenshot_img = cv2.imdecode(screenshot_array, cv2.IMREAD_COLOR)
    icon_img = cv2.imdecode(icon_array, cv2.IMREAD_COLOR)
    
    if screenshot_img is None or icon_img is None:
        log.error("CLAUDE: Failed to decode images")
        return [], []
    
    log.info(f"CLAUDE: Screenshot size: {screenshot_img.shape[:2]}, Icon size: {icon_img.shape[:2]}")
    
    # Convert to grayscale
    screenshot_gray = cv2.cvtColor(screenshot_img, cv2.COLOR_BGR2GRAY)
    icon_gray = cv2.cvtColor(icon_img, cv2.COLOR_BGR2GRAY)
    
    # Initialize SIFT detector
    sift = cv2.SIFT_create()
    
    # Find keypoints and descriptors
    kp1, des1 = sift.detectAndCompute(icon_gray, None)
    kp2, des2 = sift.detectAndCompute(screenshot_gray, None)
    
    log.info(f"CLAUDE: Icon keypoints: {len(kp1) if kp1 else 0}, Screenshot keypoints: {len(kp2) if kp2 else 0}")
    
    if des1 is None or des2 is None:
        log.warning("CLAUDE: No descriptors found - images may be too simple or uniform")
        return [], []
    
    # Match features
    matcher = cv2.BFMatcher()
    matches = matcher.knnMatch(des1, des2, k=2)
    
    log.info(f"CLAUDE: Initial matches found: {len(matches)}")
    
    # Apply Lowe's ratio test
    good_matches = []
    for match_pair in matches:
        if len(match_pair) == 2:
            m, n = match_pair
            if m.distance < ratio_threshold * n.distance:
                good_matches.append(m)
    
    log.info(f"CLAUDE: Good matches after ratio test: {len(good_matches)} (need >= {min_matches})")
    
    if len(good_matches) >= min_matches:
        # Get matched keypoints
        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        
        # Find homography
        M, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        
        if M is not None:
            # Get icon corners
            h, w = icon_gray.shape
            corners = np.float32([[0,0], [w,0], [w,h], [0,h]]).reshape(-1, 1, 2)
            
            # Transform corners to screenshot space
            transformed_corners = cv2.perspectiveTransform(corners, M)
            
            # Calculate center
            center_x = int(np.mean(transformed_corners[:, 0, 0]))
            center_y = int(np.mean(transformed_corners[:, 0, 1]))
            
            log.info(f"CLAUDE: SIFT match found at center: ({center_x}, {center_y})")
            return [(center_x, center_y)], [float(len(good_matches))]
        else:
            log.warning("CLAUDE: Homography calculation failed")
    else:
        log.info("CLAUDE: Not enough good matches for reliable detection")
    
    return [], []


def find_icon_locations_orb(screenshot_bytes: bytes, icon_bytes: bytes, min_matches: int = 2, max_matches: int = 10, distance_threshold: float = 80.0):
    """Find multiple icon locations using ORB feature matching - scale invariant, returns multiple matches."""
    import cv2
    import numpy as np
    from sklearn.cluster import DBSCAN
    
    log.info(f"CLAUDE: ORB detection starting with min_matches={min_matches}, max_matches={max_matches}, distance_threshold={distance_threshold}")
    
    # Decode images
    screenshot_array = np.frombuffer(screenshot_bytes, np.uint8)
    icon_array = np.frombuffer(icon_bytes, np.uint8)
    screenshot_img = cv2.imdecode(screenshot_array, cv2.IMREAD_COLOR)
    icon_img = cv2.imdecode(icon_array, cv2.IMREAD_COLOR)
    
    if screenshot_img is None or icon_img is None:
        log.error("CLAUDE: Failed to decode images")
        return [], []
    
    log.info(f"CLAUDE: Screenshot size: {screenshot_img.shape[:2]}, Icon size: {icon_img.shape[:2]}")
    
    # Convert to grayscale
    screenshot_gray = cv2.cvtColor(screenshot_img, cv2.COLOR_BGR2GRAY)
    icon_gray = cv2.cvtColor(icon_img, cv2.COLOR_BGR2GRAY)
    
    # Initialize ORB detector with settings optimized for small icons
    orb = cv2.ORB_create(
        nfeatures=2000,    # More features to detect
        scaleFactor=1.1,   # Smaller scale steps for small icons
        nlevels=12,        # More pyramid levels
        edgeThreshold=15,  # Lower edge threshold for small features
        patchSize=15       # Smaller patch size for small icons
    )
    
    # Find keypoints and descriptors
    kp1, des1 = orb.detectAndCompute(icon_gray, None)
    kp2, des2 = orb.detectAndCompute(screenshot_gray, None)
    
    log.info(f"CLAUDE: Icon keypoints: {len(kp1) if kp1 else 0}, Screenshot keypoints: {len(kp2) if kp2 else 0}")
    
    if des1 is None or des2 is None:
        log.warning("CLAUDE: No descriptors found - images may be too simple or uniform")
        return [], []
    
    # Match features using BFMatcher with Hamming distance for ORB
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = matcher.match(des1, des2)
    
    # Filter matches by distance threshold
    good_matches = [m for m in matches if m.distance <= distance_threshold]
    
    # Sort matches by distance (best matches first)
    good_matches = sorted(good_matches, key=lambda x: x.distance)
    
    log.info(f"CLAUDE: Total matches found: {len(matches)}, good matches after distance filter: {len(good_matches)}")
    
    if len(good_matches) < min_matches:
        log.info(f"CLAUDE: Not enough good matches ({len(good_matches)} < {min_matches})")
        return [], []
    
    # Extract matched keypoint coordinates from good matches
    src_pts = np.array([kp1[m.queryIdx].pt for m in good_matches])
    dst_pts = np.array([kp2[m.trainIdx].pt for m in good_matches])
    
    # Cluster matched points to find multiple instances
    # Use DBSCAN to group nearby matches
    if len(dst_pts) >= min_matches:
        try:
            # For small icons, use more flexible clustering
            # If we have very few matches, don't cluster - treat all as one instance
            if len(dst_pts) <= 6:  # Small number of matches, likely one icon
                log.info("CLAUDE: Few matches found, skipping clustering - treating as single icon")
                labels = np.zeros(len(dst_pts))  # All points in same cluster
            else:
                # Cluster based on screenshot coordinates with smaller epsilon for small icons
                clustering = DBSCAN(eps=30, min_samples=min_matches).fit(dst_pts)
                labels = clustering.labels_
            
            unique_labels = set(labels)
            if -1 in unique_labels:
                unique_labels.remove(-1)  # Remove noise cluster
                
            log.info(f"CLAUDE: Found {len(unique_labels)} potential clusters")
            
            valid_matches = []
            valid_similarities = []
            
            for label in unique_labels:
                # Get points in this cluster
                cluster_mask = (labels == label)
                cluster_src = src_pts[cluster_mask]
                cluster_dst = dst_pts[cluster_mask]
                cluster_matches = [good_matches[i] for i, mask in enumerate(cluster_mask) if mask]
                
                # For small icons, be more flexible with homography requirements
                if len(cluster_src) >= 4:  # Need at least 4 points for homography
                    # Calculate homography for this cluster
                    try:
                        M, _ = cv2.findHomography(cluster_src.reshape(-1, 1, 2), 
                                                cluster_dst.reshape(-1, 1, 2), 
                                                cv2.RANSAC, 3.0)  # Lower threshold for small icons
                        
                        if M is not None:
                            # Get icon corners
                            h, w = icon_gray.shape
                            corners = np.float32([[0,0], [w,0], [w,h], [0,h]]).reshape(-1, 1, 2)
                            
                            # Transform corners to screenshot space
                            transformed_corners = cv2.perspectiveTransform(corners, M)
                            
                            # Calculate center
                            center_x = int(np.mean(transformed_corners[:, 0, 0]))
                            center_y = int(np.mean(transformed_corners[:, 0, 1]))
                            
                            # Calculate normalized similarity (0-1)
                            # Use average match distance, normalize to 0-1 range
                            avg_distance = np.mean([m.distance for m in cluster_matches])
                            # ORB distances typically range 0-100+, normalize inversely
                            similarity = max(0.0, 1.0 - (avg_distance / 100.0))
                            
                            valid_matches.append((center_x, center_y))
                            valid_similarities.append(similarity)
                            
                            log.info(f"CLAUDE: ORB cluster match at ({center_x}, {center_y}) with {len(cluster_src)} features, similarity: {similarity:.3f}")
                        else:
                            log.warning("CLAUDE: Homography calculation failed")
                            
                    except Exception as e:
                        log.warning(f"CLAUDE: Homography failed for cluster: {e}")
                        continue
                
                elif len(cluster_src) >= 2:  # Fallback: use centroid for very few matches
                    # For very small feature sets, just use centroid of matches
                    center_x = int(np.mean(cluster_dst[:, 0]))
                    center_y = int(np.mean(cluster_dst[:, 1]))
                    
                    # Calculate similarity based on match quality
                    avg_distance = np.mean([m.distance for m in cluster_matches])
                    similarity = max(0.0, 1.0 - (avg_distance / 100.0))
                    
                    valid_matches.append((center_x, center_y))
                    valid_similarities.append(similarity)
                    
                    log.info(f"CLAUDE: ORB centroid match at ({center_x}, {center_y}) with {len(cluster_src)} features, similarity: {similarity:.3f}")
            
            # Sort by similarity and limit results
            if valid_matches:
                combined = list(zip(valid_matches, valid_similarities))
                combined.sort(key=lambda x: x[1], reverse=True)  # Sort by similarity desc
                combined = combined[:max_matches]  # Limit results
                
                valid_matches, valid_similarities = zip(*combined) if combined else ([], [])
                
            log.info(f"CLAUDE: ORB found {len(valid_matches)} valid matches")
            return list(valid_matches), list(valid_similarities)
            
        except Exception as e:
            log.error(f"CLAUDE: ORB clustering failed: {e}")
            return [], []
    
    return [], []


def find_icon_locations(screenshot_bytes: bytes, icon_bytes: bytes, threshold: float = 0.8):
    """Find icon locations using template matching."""
    import cv2
    import numpy as np
    
    log.info(f"CLAUDE: Template matching starting with threshold={threshold}")
    
    # Convert bytes to numpy arrays
    screenshot_array = np.frombuffer(screenshot_bytes, np.uint8)
    icon_array = np.frombuffer(icon_bytes, np.uint8)
    # Decode images
    screenshot_img = cv2.imdecode(screenshot_array, cv2.IMREAD_COLOR)
    icon_img = cv2.imdecode(icon_array, cv2.IMREAD_COLOR)
    
    if screenshot_img is None or icon_img is None:
        log.error("CLAUDE: Failed to decode images for template matching")
        return [], []
    
    # Get dimensions
    icon_h, icon_w = icon_img.shape[:2]
    screenshot_h, screenshot_w = screenshot_img.shape[:2]
    
    log.info(f"CLAUDE: Template matching - Screenshot: {screenshot_w}x{screenshot_h}, Icon: {icon_w}x{icon_h}")
    
    # Template matching
    result = cv2.matchTemplate(screenshot_img, icon_img, cv2.TM_CCOEFF_NORMED)
    
    # Find best match value for debugging
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
    log.info(f"CLAUDE: Template matching max similarity: {max_val:.3f} at {max_loc}")
    
    # Find locations above threshold
    locations = np.where(result >= threshold)
    points = list(zip(locations[1], locations[0]))  # (x, y)
    
    log.info(f"CLAUDE: Found {len(points)} points above threshold {threshold}")
    
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
            log.info(f"CLAUDE: Valid match at ({center_x}, {center_y}) with similarity {result[y, x]:.3f}")
        else:
            log.info(f"CLAUDE: Filtered out match at ({x}, {y}) - would extend outside bounds")
    
    log.info(f"CLAUDE: Template matching found {len(valid_points)} valid matches")
    return valid_points, valid_similarities


@mcp.tool()
async def find_icon(icon_base64: str, screenshot_base64: str, offset_x: int = 0, offset_y: int = 0, threshold: float = 0.5, max_results: int = 50, use_sift: bool = True, sift_min_matches: int = 4, sift_ratio: float = 0.8, use_orb: bool = True, orb_min_matches: int = 2, orb_max_matches: int = 10, orb_distance_threshold: float = 80.0):
    """Find icon locations in provided screenshot data using base64 encoded icon."""
    try:
        log.info(f"Starting icon search with base64 icon data (SIFT: {use_sift}, ORB: {use_orb})")
        screenshot_bytes = base64.b64decode(screenshot_base64)
        icon_bytes = base64.b64decode(icon_base64)
        
        locations = []
        similarities = []
        method_used = "template"  # Default assumption
        
        # Try ORB first if enabled (since it can find multiple matches)
        if use_orb:
            try:
                log.info(f"Trying ORB feature matching (min_matches={orb_min_matches}, max_matches={orb_max_matches}, distance_threshold={orb_distance_threshold})...")
                locations, similarities = find_icon_locations_orb(screenshot_bytes, icon_bytes, min_matches=orb_min_matches, max_matches=orb_max_matches, distance_threshold=orb_distance_threshold)
                if locations:
                    method_used = "orb"
                    log.info(f"ORB found {len(locations)} matches")
                else:
                    log.info("ORB found no matches, trying other methods...")
            except Exception as orb_error:
                log.warning(f"ORB failed: {orb_error}, trying other methods...")
        
        # Try SIFT if ORB didn't find anything and SIFT is enabled
        if not locations and use_sift:
            try:
                log.info(f"Trying SIFT feature matching (min_matches={sift_min_matches}, ratio={sift_ratio})...")
                locations, similarities = find_icon_locations_sift(screenshot_bytes, icon_bytes, min_matches=sift_min_matches, ratio_threshold=sift_ratio)
                if locations:
                    method_used = "sift"
                    log.info(f"SIFT found {len(locations)} matches")
                else:
                    log.info("SIFT found no matches, falling back to template matching")
            except Exception as sift_error:
                log.warning(f"SIFT failed: {sift_error}, falling back to template matching")
        
        # Fall back to template matching if no feature matching found anything
        if not locations:
            log.info("Using template matching...")
            locations, similarities = find_icon_locations(screenshot_bytes, icon_bytes, threshold=threshold)
            method_used = "template"
        
        # Apply offset
        locations = [(x + offset_x, y + offset_y) for x, y in locations]

        if max_results and locations:
            # sort by similarity and limit results
            sorted_results = sorted(zip(locations, similarities), key=lambda item: item[1],
                                    reverse=True)[:max_results]
            locations, similarities = zip(*sorted_results) if sorted_results else ([], [])

        log.info(f"Found {len(locations)} total icon matches using {method_used}")
        return {
            "locations": locations,
            "similarities": similarities,
            "method_used": method_used
        }
    except Exception as e:
        log.error(f"Icon search failed: {e}")
        return {
            "error": f"Icon search failed: {str(e)}", 
            "locations": [],
            "similarities": [],
            "method_used": "error"
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
        
        log.info("Converting bytes to numpy array...")
        # Convert bytes to numpy array for PaddleOCR
        nparr = np.frombuffer(screenshot_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        log.info("Running OCR prediction with numpy array...")
        result = ocr.predict(input=img)

        # Extract detection results from predict() format
        detections = []
        for res in result:
            # OCRResult is a dictionary-like object
            rec_texts = res['rec_texts']
            rec_polys = res['rec_polys']  
            rec_scores = res['rec_scores']
            
            # Combine texts, boxes and scores
            for text, box, score in zip(rec_texts, rec_polys, rec_scores):
                # Convert numpy array box to list of points
                box_points = box.tolist()
                detections.append([box_points, (text, score)])
        
        log.info(f"OCR prediction completed - found {len(detections)} text detections")
        return detections
        
    except Exception as e:
        log.error(f"OCR failed: {str(e)}")
        raise


@mcp.tool()
async def get_all_text(screenshot_base64: str, offset_x: int = 0, offset_y: int = 0, format: str = "json"):
    """Get all detected text from screenshot data. Format can be 'json' or 'csv'."""
    log.info("Starting OCR to get all detected text")
    
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
                "all_text": []
            }
        finally:
            executor.shutdown(wait=True)
            
    except Exception as e:
        log.error(f"Get all text failed: {e}")
        return {
            "error": f"Get all text failed: {str(e)}", 
            "all_text": []
        }
    
    # Process all detected text with locations
    all_text = []
    for detection in result:
        box, (text_rec, confidence) = detection
        # box is a list of 4 corner points [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        # Calculate center from bounding box
        x_coords = [point[0] for point in box]
        y_coords = [point[1] for point in box]
        center_x = int(sum(x_coords) / len(x_coords)) + offset_x
        center_y = int(sum(y_coords) / len(y_coords)) + offset_y
        all_text.append({
            "text": text_rec,
            "confidence": float(confidence),
            "x": center_x,
            "y": center_y,
        })
    
    log.info(f"Found {len(all_text)} total text detections")
    
    if format.lower() == "csv":
        import io
        csv_output = io.StringIO()
        csv_output.write("text,x,y,confidence\n")
        for item in all_text:
            # Escape quotes in text by doubling them, wrap in quotes
            escaped_text = item["text"].replace('"', '""')
            csv_output.write(f'"{escaped_text}",{item["x"]},{item["y"]},{item["confidence"]}\n')
        return {
            "format": "csv",
            "data": csv_output.getvalue()
        }
    else:
        return {
            "format": "json",
            "all_text": all_text
        }


@mcp.tool()
async def find_text(text: str, screenshot_base64: str, offset_x: int = 0, offset_y: int = 0, format: str = "json"):
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
    matches = []
    for detection in result:
        box, (text_rec, confidence) = detection
        if text.lower() in text_rec.lower():
            # box is a list of 4 corner points [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
            # Calculate center from bounding box
            x_coords = [point[0] for point in box]
            y_coords = [point[1] for point in box]
            center_x = int(sum(x_coords) / len(x_coords)) + offset_x
            center_y = int(sum(y_coords) / len(y_coords)) + offset_y
            matches.append({
                "text": text_rec,
                "confidence": float(confidence),
                "x": center_x,
                "y": center_y,
            })
    
    log.info(f"Found {len(matches)} text matches")
    
    if format.lower() == "csv":
        import io
        csv_output = io.StringIO()
        csv_output.write("text,x,y,confidence\n")
        for item in matches:
            # Escape quotes in text by doubling them, wrap in quotes
            escaped_text = item["text"].replace('"', '""')
            csv_output.write(f'"{escaped_text}",{item["x"]},{item["y"]},{item["confidence"]}\n')
        return {
            "format": "csv",
            "data": csv_output.getvalue()
        }
    else:
        # Convert to old format for backward compatibility
        locations = []
        confidences = []
        for match in matches:
            locations.append({
                "text": match["text"],
                "location": {
                    "x": match["x"],
                    "y": match["y"],
                }
            })
            confidences.append(match["confidence"])
        
        return {
            "format": "json",
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

import cv2
import numpy as np
from paddleocr import PaddleOCR
import logging
import json

# Configure logging
logging.basicConfig(level=logging.ERROR) 
logger = logging.getLogger(__name__)

def create_test_image(gap):
    # Create valid white image
    img = np.ones((100, 800, 3), dtype=np.uint8) * 255
    
    # "Label" approx width 90px. Ends at 50+90=140 roughly.
    start_x = 50
    cv2.putText(img, "Label", (start_x, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    
    # Calculate end of first word roughly
    label_size = cv2.getTextSize("Label", cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
    end_x = start_x + label_size[0]
    
    second_word_x = end_x + gap
    cv2.putText(img, "Value", (second_word_x, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    
    return img

def test_ocr(gap, unclip_ratio=1.5):
    img = create_test_image(gap)
    
    try:
        # Initialize PaddleOCR
        # NOTE: show_log removed
        ocr = PaddleOCR(
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            lang='en',
            det_db_unclip_ratio=unclip_ratio
        )
        
        result = ocr.predict(input=img)
        
        detections = []
        texts = []
        if result:
            for res in result:
                rec_texts = res['rec_texts']
                if rec_texts:
                    texts.extend(rec_texts)

        merged = False
        # If we have only 1 detection and it contains both words or they are combined
        # Since we use simple "Label" and "Value"
        if len(texts) == 1:
             # Check if the single text contains both parts roughly
             if "Label" in texts[0] and "Value" in texts[0]:
                 merged = True
             if "LabelValue" in texts[0].replace(" ", ""):
                 merged = True
        
        print(f"Gap: {gap}px, Unclip: {unclip_ratio} -> Detected: {texts}. Merged: {merged}")
        
    except Exception as e:
        print(f"Error with gap {gap}, unclip {unclip_ratio}: {e}")

if __name__ == "__main__":
    gaps = [10, 20, 30, 40, 50, 100]
    # Some typical values to try
    unclip_ratios = [1.5, 2.0, 1.2, 1.0] # 1.5 is default usually
    
    print("Testing different gaps and unclip ratios...")
    for unclip in unclip_ratios:
        print(f"\n--- Testing unclip_ratio={unclip} ---")
        for gap in gaps:
            test_ocr(gap, unclip)

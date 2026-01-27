
import pytest
import base64
import cv2
import numpy as np
from adare.helperfunctions.image import calculate_pixel_change

@pytest.fixture
def black_image_base64():
    """Create a 100x100 black image base64 string"""
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    _, buffer = cv2.imencode('.png', img)
    return base64.b64encode(buffer).decode('utf-8')

@pytest.fixture
def white_image_base64():
    """Create a 100x100 white image base64 string"""
    img = np.ones((100, 100, 3), dtype=np.uint8) * 255
    _, buffer = cv2.imencode('.png', img)
    return base64.b64encode(buffer).decode('utf-8')

@pytest.fixture
def half_white_image_base64():
    """Create a 100x100 image where left half is black, right half is white"""
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[:, 50:] = 255
    _, buffer = cv2.imencode('.png', img)
    return base64.b64encode(buffer).decode('utf-8')

def test_pixel_change_identical(black_image_base64):
    """Test 0% change for identical images"""
    change = calculate_pixel_change(black_image_base64, black_image_base64)
    assert change == 0.0

def test_pixel_change_full(black_image_base64, white_image_base64):
    """Test 100% change for completely different images"""
    change = calculate_pixel_change(black_image_base64, white_image_base64)
    assert change == 100.0

def test_pixel_change_half(black_image_base64, half_white_image_base64):
    """Test 50% change"""
    change = calculate_pixel_change(black_image_base64, half_white_image_base64)
    assert change == 50.0

def test_pixel_change_resize():
    """Test automatic resizing if dimensions differ"""
    # Create 50x50 black image
    img_small = np.zeros((50, 50, 3), dtype=np.uint8)
    _, buffer_small = cv2.imencode('.png', img_small)
    small_base64 = base64.b64encode(buffer_small).decode('utf-8')
    
    # Create 100x100 white image
    img_large = np.ones((100, 100, 3), dtype=np.uint8) * 255
    _, buffer_large = cv2.imencode('.png', img_large)
    large_base64 = base64.b64encode(buffer_large).decode('utf-8')
    
    # Needs resize, resulting in comparing black vs white (100% diff)
    change = calculate_pixel_change(small_base64, large_base64)
    assert change == 100.0

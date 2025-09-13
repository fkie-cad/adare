"""Custom exceptions for the Adare MCP Server."""


class AdareServerError(Exception):
    """Base exception for Adare MCP Server errors."""
    pass


class ImageDecodingError(AdareServerError):
    """Raised when image decoding fails."""
    pass


class FeatureMatchingError(AdareServerError):
    """Raised when feature matching algorithms fail."""
    pass


class OCRProcessingError(AdareServerError):
    """Raised when OCR processing fails."""
    pass


class HomographyCalculationError(AdareServerError):
    """Raised when homography calculation fails."""
    pass
# Adare MCP Server

MCP server for computer vision and OCR capabilities for the Adare testing framework.

## Features

### Image Processing
- **Multi-Method Aggregated Detection**: Runs all applicable detection methods and aggregates results for maximum robustness
- **Feature Matching**: SIFT, ORB, Canny edge, and multi-scale template matching algorithms
- **Format Support**: PNG, JPEG, BMP, and **SVG** (with automatic conversion)
- **SVG Handling**: Transparent conversion of SVG images to PNG for OpenCV processing

### Detection Pipeline Architecture

**Parallel Aggregated Pipeline** (replaces early-exit staging):

1. **Stage 0**: Canny edge-based multi-scale template matching (0.85 threshold, 0.1-10.0x scale)
   - Lighting-invariant detection using structural outlines (ignores color/intensity)
   - Robust to theme changes (light/dark mode), color variations, tint differences
   - ~50-560ms (28 scales, early termination on >0.95 match)

2. **Stage 1**: Multi-scale template matching (0.9 threshold, 0.1-10.0x scale)
   - Pixel-exact matching across extreme scale range (10% to 1000%)
   - Acts as precision gate to prevent ORB false positives on text edges
   - ~20-560ms (28 scales, early termination optimization)

3. **Stage 2**: Laplacian variance gatekeeper (threshold: 0.5)
   - Analyzes icon texture complexity to determine ORB suitability
   - Flat icons (variance <0.5) skip ORB to avoid matching text edges
   - Textured icons (variance >0.5) proceed to ORB

4. **Stage 3**: ORB feature matching (textured icons only)
   - Handles scaled/rotated complex icons (~30-80ms)
   - Only runs if Stage 2 approves (prevents false positives)

5. **Stage 4**: SIFT fallback
   - Most robust for gradient/complex icons that failed ORB (~80-120ms)

6. **Stage 5**: Template matching at 0.75 threshold (catch-all)
   - Final attempt with relaxed threshold (~10-20ms)

**Aggregation Strategy**:
- All applicable methods run (no early exits except ORB gatekeeper)
- Results weighted by method precision: Canny (1.0) > Multi-scale (0.95) > SIFT (0.90) > ORB (0.85) > Template (0.80)
- Global NMS removes cross-method duplicates (IoU threshold: 0.5)
- Returns all unique detections with method provenance
- SIFT match counts normalized to 0.0-1.0 range (20+ matches = 1.0)

**Performance**:
- Total pipeline: ~200ms-1350ms (all methods, deterministic)
- Acceptable for forensic analysis (accuracy > speed)
- No false negatives from early exit (all methods run)

**Benefits**:
- ✅ Prevents false negatives (Canny misses + template finds = detected)
- ✅ Method diversity increases robustness across icon types
- ✅ Forensic auditability (track which methods detected each icon)
- ✅ Confidence ranking via weighted similarities
- ✅ Precision maintained via global NMS (no duplicate reporting)

### OCR Processing
- **Text Detection**: PaddleOCR-based text extraction from screenshots
- **SVG Screenshots**: Full support for SVG format screenshots in OCR operations
- **Advanced Matching**: Substring, regex, fuzzy, and hybrid matching modes

## Installation

### Python Dependencies

```bash
cd adare-cv-server
poetry install
```

### System Dependencies (Linux only)

For SVG support on Linux, install Cairo libraries:

```bash
# Ubuntu/Debian
sudo apt install libcairo2-dev libpango1.0-dev

# Fedora/RHEL
sudo dnf install cairo-devel pango-devel
```

**Note**: Windows and macOS users don't need additional system packages (Cairo is bundled with the wheel).

## SVG Support

### Overview

The server automatically detects and converts SVG images to PNG before processing with OpenCV. This is completely transparent to the user - no API changes required.

### How It Works

1. **Detection**: Checks for SVG magic bytes (`<?xml` or `<svg`)
2. **Conversion**: Uses CairoSVG to convert SVG → PNG in memory
3. **Processing**: Passes PNG to OpenCV for feature matching or OCR

### Supported Operations

All MCP tools support SVG format:

- `find_icon_in_screenshot` - Feature matching with SVG icons
- `get_all_text` - OCR processing of SVG screenshots
- `find_text` - Text search in SVG screenshots

### Usage Examples

**Feature Matching with SVG Icon:**
```python
# Icon can be SVG - automatically converted to PNG
result = await find_icon_in_screenshot(
    screenshot_bytes=screenshot_png,
    icon_bytes=icon_svg,  # SVG format
    method="sift"
)
```

**OCR on SVG Screenshot:**
```python
# Screenshot can be SVG - automatically converted to PNG
result = await get_all_text(
    screenshot_bytes=screenshot_svg  # SVG format
)
```

### Performance

- **First conversion**: ~50-200ms depending on SVG complexity
- **Memory overhead**: Minimal (in-memory conversion)
- **Non-SVG images**: Zero overhead (detection is fast)

### SVG Icon Optimization

The server automatically optimizes SVG icons for feature matching:

**Small Icons (<100px)**:
- Upscaled 4x (e.g., 48x48 → 192x192) for better feature detection
- Converted with white background for contrast
- ORB uses reduced pyramid levels (6 vs 12) to prevent over-downsampling
- Edge threshold relaxed (5px vs 15px) to detect central features

**Large SVG Screenshots**:
- Original dimensions preserved
- Standard ORB parameters (12 levels, 15px edge threshold)

**Why This Matters**:
- Small SVG icons often have flat colors and minimal texture
- ORB/SIFT need sufficient pixel density to detect corners/edges
- Upscaling provides more detail without changing visual appearance
- White background prevents transparent edge artifacts

### Limitations

- **Large SVGs**: Very complex SVGs (>10MB) may take longer to convert
- **Text rendering**: SVG text elements are rasterized (may affect OCR accuracy vs native text)
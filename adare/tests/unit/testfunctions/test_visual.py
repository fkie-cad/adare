"""Comprehensive unit tests for Visual testfunctions."""

import pytest
import sys
from pathlib import Path
from unittest.mock import AsyncMock

# Add paths for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ADARELIB_ROOT = PROJECT_ROOT.parent / "adarelib"

# Add to sys.path if not already there
if str(ADARELIB_ROOT) not in sys.path:
    sys.path.insert(0, str(ADARELIB_ROOT))

# Import from adarelib.constants as required
from adarelib.constants import StatusEnum

# Import testfunctions dynamically
from adare.helperfunctions.module import import_module_from_pyfile

# Load visual testfunctions module
visual_module_path = PROJECT_ROOT / "appdata" / "testfunctions" / "visual" / "visual.py"
visual_module = import_module_from_pyfile(visual_module_path)

# Extract testfunctions from module (decorator pattern: access generated classes via decorated function)
VisualExists = visual_module.visual_exists._test_class
VisualExistsParameter = visual_module.visual_exists._parameter_class
VisualNotExists = visual_module.visual_not_exists._test_class
VisualNotExistsParameter = visual_module.visual_not_exists._parameter_class
VisualCountEquals = visual_module.visual_count_equals._test_class
VisualCountEqualsParameter = visual_module.visual_count_equals._parameter_class
VisualCountMin = visual_module.visual_count_min._test_class
VisualCountMinParameter = visual_module.visual_count_min._parameter_class
VisualCountMax = visual_module.visual_count_max._test_class
VisualCountMaxParameter = visual_module.visual_count_max._parameter_class


# Import test helpers
import importlib.util
helpers_path = Path(__file__).parent / "helpers.py"
spec = importlib.util.spec_from_file_location("helpers", helpers_path)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

assert_test_success = helpers.assert_test_success
assert_test_failed = helpers.assert_test_failed
assert_test_error = helpers.assert_test_error
assert_test_execution_error = helpers.assert_test_execution_error


# ============================================================================
# VisualExists Tests
# ============================================================================

class TestVisualExists:
    """Tests for VisualExists testfunction."""

    @pytest.mark.asyncio
    async def test_visual_exists_text_found(self, mock_visual_context):
        """Test successful text detection."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[(100, 200)])

        test = VisualExists(
            name="test_text_exists",
            parameter=VisualExistsParameter(text="Hello World")
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)
        mock_visual_context.screenshot.take.assert_called_once()
        mock_visual_context.cv.find_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_visual_exists_text_not_found(self, mock_visual_context):
        """Test failure when text not detected."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[])

        test = VisualExists(
            name="test_text_exists",
            parameter=VisualExistsParameter(text="Not Found")
        )
        result = await test.test(mock_visual_context)

        assert_test_failed(result)
        assert "Visual element not found" in result.details[0]
        assert "text 'Not Found'" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_exists_text_multiple_matches(self, mock_visual_context):
        """Test text found multiple times (still success)."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[(10, 20), (30, 40), (50, 60)])

        test = VisualExists(
            name="test_text_exists",
            parameter=VisualExistsParameter(text="Repeated")
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)

    @pytest.mark.asyncio
    async def test_visual_exists_image_found(self, mock_visual_context, tmp_path):
        """Test successful image detection."""
        image_file = tmp_path / "icon.png"
        image_file.write_bytes(b"fake_image_data")

        mock_visual_context.playbook_dir = tmp_path
        mock_visual_context.cv.find_icon = AsyncMock(return_value=[(150, 250)])

        test = VisualExists(
            name="test_image_exists",
            parameter=VisualExistsParameter(image="icon.png")
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)
        mock_visual_context.cv.find_icon.assert_called_once()

    @pytest.mark.asyncio
    async def test_visual_exists_image_not_found(self, mock_visual_context, tmp_path):
        """Test failure when image not detected."""
        image_file = tmp_path / "icon.png"
        image_file.write_bytes(b"fake_image_data")

        mock_visual_context.playbook_dir = tmp_path
        mock_visual_context.cv.find_icon = AsyncMock(return_value=[])

        test = VisualExists(
            name="test_image_exists",
            parameter=VisualExistsParameter(image="icon.png")
        )
        result = await test.test(mock_visual_context)

        assert_test_failed(result)
        assert "Visual element not found" in result.details[0]
        assert "image 'icon.png'" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_exists_image_absolute_path(self, mock_visual_context, tmp_path):
        """Test image detection with absolute path."""
        image_file = tmp_path / "icon.png"
        image_file.write_bytes(b"fake_image_data")

        mock_visual_context.cv.find_icon = AsyncMock(return_value=[(200, 300)])

        test = VisualExists(
            name="test_image_exists",
            parameter=VisualExistsParameter(image=str(image_file))
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)

    @pytest.mark.asyncio
    async def test_visual_exists_image_file_not_found(self, mock_visual_context, tmp_path):
        """Test execution error when image file doesn't exist."""
        mock_visual_context.playbook_dir = tmp_path
        mock_visual_context.cv.find_icon = AsyncMock(side_effect=FileNotFoundError("File not found"))

        test = VisualExists(
            name="test_image_exists",
            parameter=VisualExistsParameter(image="nonexistent.png")
        )
        result = await test.test(mock_visual_context)

        assert_test_execution_error(result)
        assert "Image file not found" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_exists_no_parameters_error(self, mock_visual_context):
        """Test execution error when neither text nor image provided."""
        test = VisualExists(
            name="test_invalid",
            parameter=VisualExistsParameter()
        )
        result = await test.test(mock_visual_context)

        assert_test_error(result)
        assert "Either text or image parameter required" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_exists_with_window_parameter(self, mock_visual_context):
        """Test text detection with specific window."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[(100, 200)])

        test = VisualExists(
            name="test_window",
            parameter=VisualExistsParameter(text="Title", window="Firefox")
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)
        mock_visual_context.screenshot.take.assert_called_once_with(window="Firefox")


# ============================================================================
# VisualNotExists Tests
# ============================================================================

class TestVisualNotExists:
    """Tests for VisualNotExists testfunction."""

    @pytest.mark.asyncio
    async def test_visual_not_exists_text_success(self, mock_visual_context):
        """Test successful check that text is not present."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[])

        test = VisualNotExists(
            name="test_text_not_exists",
            parameter=VisualNotExistsParameter(text="Should Not Exist")
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)

    @pytest.mark.asyncio
    async def test_visual_not_exists_text_failure_found(self, mock_visual_context):
        """Test failure when text is found but shouldn't be."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[(100, 200)])

        test = VisualNotExists(
            name="test_text_not_exists",
            parameter=VisualNotExistsParameter(text="Found Text")
        )
        result = await test.test(mock_visual_context)

        assert_test_failed(result)
        assert "should not exist but was found" in result.details[0]
        assert "text 'Found Text'" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_not_exists_text_multiple_found(self, mock_visual_context):
        """Test failure when multiple instances found."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[(10, 20), (30, 40)])

        test = VisualNotExists(
            name="test_text_not_exists",
            parameter=VisualNotExistsParameter(text="Multiple")
        )
        result = await test.test(mock_visual_context)

        assert_test_failed(result)
        assert "should not exist but was found" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_not_exists_image_success(self, mock_visual_context, tmp_path):
        """Test successful check that image is not present."""
        image_file = tmp_path / "icon.png"
        image_file.write_bytes(b"fake_image_data")

        mock_visual_context.playbook_dir = tmp_path
        mock_visual_context.cv.find_icon = AsyncMock(return_value=[])

        test = VisualNotExists(
            name="test_image_not_exists",
            parameter=VisualNotExistsParameter(image="icon.png")
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)

    @pytest.mark.asyncio
    async def test_visual_not_exists_image_failure_found(self, mock_visual_context, tmp_path):
        """Test failure when image is found but shouldn't be."""
        image_file = tmp_path / "icon.png"
        image_file.write_bytes(b"fake_image_data")

        mock_visual_context.playbook_dir = tmp_path
        mock_visual_context.cv.find_icon = AsyncMock(return_value=[(150, 250)])

        test = VisualNotExists(
            name="test_image_not_exists",
            parameter=VisualNotExistsParameter(image="icon.png")
        )
        result = await test.test(mock_visual_context)

        assert_test_failed(result)
        assert "should not exist but was found" in result.details[0]
        assert "image 'icon.png'" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_not_exists_no_parameters_error(self, mock_visual_context):
        """Test error when neither text nor image provided."""
        test = VisualNotExists(
            name="test_invalid",
            parameter=VisualNotExistsParameter()
        )
        result = await test.test(mock_visual_context)

        assert_test_error(result)
        assert "Either text or image parameter required" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_not_exists_with_window_parameter(self, mock_visual_context):
        """Test image not present check with specific window."""
        mock_visual_context.playbook_dir = Path("/fake/dir")
        mock_visual_context.cv.find_icon = AsyncMock(return_value=[])

        test = VisualNotExists(
            name="test_window",
            parameter=VisualNotExistsParameter(image="button.png", window="Chrome")
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)
        mock_visual_context.screenshot.take.assert_called_once_with(window="Chrome")


# ============================================================================
# VisualCountEquals Tests
# ============================================================================

class TestVisualCountEquals:
    """Tests for VisualCountEquals testfunction."""

    @pytest.mark.asyncio
    async def test_visual_count_equals_text_success(self, mock_visual_context):
        """Test successful exact count match for text."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[(10, 20), (30, 40), (50, 60)])

        test = VisualCountEquals(
            name="test_count_equals",
            parameter=VisualCountEqualsParameter(text="Item", n=3)
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)

    @pytest.mark.asyncio
    async def test_visual_count_equals_text_zero(self, mock_visual_context):
        """Test exact count of zero."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[])

        test = VisualCountEquals(
            name="test_count_equals",
            parameter=VisualCountEqualsParameter(text="None", n=0)
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)

    @pytest.mark.asyncio
    async def test_visual_count_equals_text_failure_too_few(self, mock_visual_context):
        """Test failure when count is less than expected."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[(10, 20)])

        test = VisualCountEquals(
            name="test_count_equals",
            parameter=VisualCountEqualsParameter(text="Item", n=3)
        )
        result = await test.test(mock_visual_context)

        assert_test_failed(result)
        assert "count mismatch" in result.details[0]
        assert "expected 3, found 1" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_count_equals_text_failure_too_many(self, mock_visual_context):
        """Test failure when count is more than expected."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[(10, 20), (30, 40), (50, 60), (70, 80)])

        test = VisualCountEquals(
            name="test_count_equals",
            parameter=VisualCountEqualsParameter(text="Item", n=2)
        )
        result = await test.test(mock_visual_context)

        assert_test_failed(result)
        assert "count mismatch" in result.details[0]
        assert "expected 2, found 4" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_count_equals_image_success(self, mock_visual_context, tmp_path):
        """Test successful exact count match for image."""
        image_file = tmp_path / "icon.png"
        image_file.write_bytes(b"fake_image_data")

        mock_visual_context.playbook_dir = tmp_path
        mock_visual_context.cv.find_icon = AsyncMock(return_value=[(100, 200), (300, 400)])

        test = VisualCountEquals(
            name="test_count_equals",
            parameter=VisualCountEqualsParameter(image="icon.png", n=2)
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)

    @pytest.mark.asyncio
    async def test_visual_count_equals_image_failure(self, mock_visual_context, tmp_path):
        """Test failure when image count doesn't match."""
        image_file = tmp_path / "icon.png"
        image_file.write_bytes(b"fake_image_data")

        mock_visual_context.playbook_dir = tmp_path
        mock_visual_context.cv.find_icon = AsyncMock(return_value=[(100, 200)])

        test = VisualCountEquals(
            name="test_count_equals",
            parameter=VisualCountEqualsParameter(image="icon.png", n=5)
        )
        result = await test.test(mock_visual_context)

        assert_test_failed(result)
        assert "count mismatch" in result.details[0]
        assert "expected 5, found 1" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_count_equals_no_n_parameter_error(self, mock_visual_context):
        """Test error when 'n' parameter not provided."""
        test = VisualCountEquals(
            name="test_invalid",
            parameter=VisualCountEqualsParameter(text="Item")
        )
        result = await test.test(mock_visual_context)

        assert_test_error(result)
        assert "Parameter 'n' required" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_count_equals_no_search_param_error(self, mock_visual_context):
        """Test error when neither text nor image provided."""
        test = VisualCountEquals(
            name="test_invalid",
            parameter=VisualCountEqualsParameter(n=5)
        )
        result = await test.test(mock_visual_context)

        assert_test_error(result)
        assert "Either text or image parameter required" in result.details[0]


# ============================================================================
# VisualCountMin Tests
# ============================================================================

class TestVisualCountMin:
    """Tests for VisualCountMin testfunction."""

    @pytest.mark.asyncio
    async def test_visual_count_min_text_success_exact(self, mock_visual_context):
        """Test successful min count check with exact match."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[(10, 20), (30, 40)])

        test = VisualCountMin(
            name="test_count_min",
            parameter=VisualCountMinParameter(text="Item", min=2)
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)

    @pytest.mark.asyncio
    async def test_visual_count_min_text_success_more(self, mock_visual_context):
        """Test successful min count check with more than minimum."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[(10, 20), (30, 40), (50, 60), (70, 80)])

        test = VisualCountMin(
            name="test_count_min",
            parameter=VisualCountMinParameter(text="Item", min=2)
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)

    @pytest.mark.asyncio
    async def test_visual_count_min_text_success_zero(self, mock_visual_context):
        """Test min count of zero always succeeds."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[])

        test = VisualCountMin(
            name="test_count_min",
            parameter=VisualCountMinParameter(text="Item", min=0)
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)

    @pytest.mark.asyncio
    async def test_visual_count_min_text_failure(self, mock_visual_context):
        """Test failure when count is below minimum."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[(10, 20)])

        test = VisualCountMin(
            name="test_count_min",
            parameter=VisualCountMinParameter(text="Item", min=3)
        )
        result = await test.test(mock_visual_context)

        assert_test_failed(result)
        assert "below minimum" in result.details[0]
        assert "expected >= 3, found 1" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_count_min_text_failure_zero_found(self, mock_visual_context):
        """Test failure when zero found but minimum is higher."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[])

        test = VisualCountMin(
            name="test_count_min",
            parameter=VisualCountMinParameter(text="Item", min=1)
        )
        result = await test.test(mock_visual_context)

        assert_test_failed(result)
        assert "below minimum" in result.details[0]
        assert "expected >= 1, found 0" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_count_min_image_success(self, mock_visual_context, tmp_path):
        """Test successful min count check for image."""
        image_file = tmp_path / "icon.png"
        image_file.write_bytes(b"fake_image_data")

        mock_visual_context.playbook_dir = tmp_path
        mock_visual_context.cv.find_icon = AsyncMock(return_value=[(100, 200), (300, 400), (500, 600)])

        test = VisualCountMin(
            name="test_count_min",
            parameter=VisualCountMinParameter(image="icon.png", min=2)
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)

    @pytest.mark.asyncio
    async def test_visual_count_min_image_failure(self, mock_visual_context, tmp_path):
        """Test failure when image count is below minimum."""
        image_file = tmp_path / "icon.png"
        image_file.write_bytes(b"fake_image_data")

        mock_visual_context.playbook_dir = tmp_path
        mock_visual_context.cv.find_icon = AsyncMock(return_value=[(100, 200)])

        test = VisualCountMin(
            name="test_count_min",
            parameter=VisualCountMinParameter(image="icon.png", min=4)
        )
        result = await test.test(mock_visual_context)

        assert_test_failed(result)
        assert "below minimum" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_count_min_no_min_parameter_error(self, mock_visual_context):
        """Test error when 'min' parameter not provided."""
        test = VisualCountMin(
            name="test_invalid",
            parameter=VisualCountMinParameter(text="Item")
        )
        result = await test.test(mock_visual_context)

        assert_test_error(result)
        assert "Parameter 'min' required" in result.details[0]


# ============================================================================
# VisualCountMax Tests
# ============================================================================

class TestVisualCountMax:
    """Tests for VisualCountMax testfunction."""

    @pytest.mark.asyncio
    async def test_visual_count_max_text_success_exact(self, mock_visual_context):
        """Test successful max count check with exact match."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[(10, 20), (30, 40)])

        test = VisualCountMax(
            name="test_count_max",
            parameter=VisualCountMaxParameter(text="Item", max=2)
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)

    @pytest.mark.asyncio
    async def test_visual_count_max_text_success_less(self, mock_visual_context):
        """Test successful max count check with less than maximum."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[(10, 20)])

        test = VisualCountMax(
            name="test_count_max",
            parameter=VisualCountMaxParameter(text="Item", max=5)
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)

    @pytest.mark.asyncio
    async def test_visual_count_max_text_success_zero_found(self, mock_visual_context):
        """Test success when zero found (always under max)."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[])

        test = VisualCountMax(
            name="test_count_max",
            parameter=VisualCountMaxParameter(text="Item", max=3)
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)

    @pytest.mark.asyncio
    async def test_visual_count_max_text_success_max_zero(self, mock_visual_context):
        """Test max of zero with zero found."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[])

        test = VisualCountMax(
            name="test_count_max",
            parameter=VisualCountMaxParameter(text="Item", max=0)
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)

    @pytest.mark.asyncio
    async def test_visual_count_max_text_failure_exceeds(self, mock_visual_context):
        """Test failure when count exceeds maximum."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[(10, 20), (30, 40), (50, 60), (70, 80)])

        test = VisualCountMax(
            name="test_count_max",
            parameter=VisualCountMaxParameter(text="Item", max=2)
        )
        result = await test.test(mock_visual_context)

        assert_test_failed(result)
        assert "exceeds maximum" in result.details[0]
        assert "expected <= 2, found 4" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_count_max_text_failure_max_zero(self, mock_visual_context):
        """Test failure when max is zero but items found."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[(10, 20)])

        test = VisualCountMax(
            name="test_count_max",
            parameter=VisualCountMaxParameter(text="Item", max=0)
        )
        result = await test.test(mock_visual_context)

        assert_test_failed(result)
        assert "exceeds maximum" in result.details[0]
        assert "expected <= 0, found 1" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_count_max_image_success(self, mock_visual_context, tmp_path):
        """Test successful max count check for image."""
        image_file = tmp_path / "icon.png"
        image_file.write_bytes(b"fake_image_data")

        mock_visual_context.playbook_dir = tmp_path
        mock_visual_context.cv.find_icon = AsyncMock(return_value=[(100, 200), (300, 400)])

        test = VisualCountMax(
            name="test_count_max",
            parameter=VisualCountMaxParameter(image="icon.png", max=5)
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)

    @pytest.mark.asyncio
    async def test_visual_count_max_image_failure(self, mock_visual_context, tmp_path):
        """Test failure when image count exceeds maximum."""
        image_file = tmp_path / "icon.png"
        image_file.write_bytes(b"fake_image_data")

        mock_visual_context.playbook_dir = tmp_path
        mock_visual_context.cv.find_icon = AsyncMock(return_value=[(100, 200), (300, 400), (500, 600)])

        test = VisualCountMax(
            name="test_count_max",
            parameter=VisualCountMaxParameter(image="icon.png", max=1)
        )
        result = await test.test(mock_visual_context)

        assert_test_failed(result)
        assert "exceeds maximum" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_count_max_no_max_parameter_error(self, mock_visual_context):
        """Test error when 'max' parameter not provided."""
        test = VisualCountMax(
            name="test_invalid",
            parameter=VisualCountMaxParameter(text="Item")
        )
        result = await test.test(mock_visual_context)

        assert_test_error(result)
        assert "Parameter 'max' required" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_count_max_no_search_param_error(self, mock_visual_context):
        """Test error when neither text nor image provided."""
        test = VisualCountMax(
            name="test_invalid",
            parameter=VisualCountMaxParameter(max=5)
        )
        result = await test.test(mock_visual_context)

        assert_test_error(result)
        assert "Either text or image parameter required" in result.details[0]


# ============================================================================
# Additional Edge Cases and Integration Tests
# ============================================================================

class TestVisualEdgeCases:
    """Additional edge case tests for Visual testfunctions."""

    @pytest.mark.asyncio
    async def test_execute_on_host_flag_is_set(self):
        """Verify that all Visual tests have execute_on_host=True."""
        assert VisualExists.execute_on_host is True
        assert VisualNotExists.execute_on_host is True
        assert VisualCountEquals.execute_on_host is True
        assert VisualCountMin.execute_on_host is True
        assert VisualCountMax.execute_on_host is True

    @pytest.mark.asyncio
    async def test_visual_exists_both_text_and_image_text_priority(self, mock_visual_context, tmp_path):
        """Test that text takes precedence when both text and image are provided."""
        image_file = tmp_path / "icon.png"
        image_file.write_bytes(b"fake_image")
        mock_visual_context.playbook_dir = tmp_path

        # Mock text finding
        mock_visual_context.cv.find_text = AsyncMock(return_value=[(100, 100)])
        mock_visual_context.cv.find_icon = AsyncMock(return_value=[])

        test = VisualExists(
            name="test_both",
            parameter=VisualExistsParameter(text="Button", image="icon.png")
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)
        # Should only call find_text, not find_icon
        mock_visual_context.cv.find_text.assert_called_once()
        mock_visual_context.cv.find_icon.assert_not_called()

    @pytest.mark.asyncio
    async def test_visual_generic_exception_handling(self, mock_visual_context):
        """Test generic exception handling in Visual tests."""
        mock_visual_context.cv.find_text = AsyncMock(side_effect=RuntimeError("Unexpected CV error"))

        test = VisualExists(
            name="test_exception",
            parameter=VisualExistsParameter(text="Test")
        )
        result = await test.test(mock_visual_context)

        assert_test_execution_error(result)
        assert "Error in testfunction 'visual.exists'" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_count_large_numbers(self, mock_visual_context):
        """Test count functions with large number of occurrences."""
        # Generate 100 location tuples
        locations = [(i * 10, i * 10) for i in range(100)]
        mock_visual_context.cv.find_text = AsyncMock(return_value=locations)

        test = VisualCountEquals(
            name="test_large_count",
            parameter=VisualCountEqualsParameter(text="Item", n=100)
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)

    @pytest.mark.asyncio
    async def test_visual_screenshot_taken_before_search(self, mock_visual_context):
        """Verify screenshot is taken before visual search."""
        call_order = []

        async def mock_screenshot(*args, **kwargs):
            call_order.append("screenshot")
            return b"fake_screenshot"

        async def mock_find_text(*args, **kwargs):
            call_order.append("find_text")
            return [(10, 10)]

        mock_visual_context.screenshot.take = mock_screenshot
        mock_visual_context.cv.find_text = mock_find_text

        test = VisualExists(
            name="test_order",
            parameter=VisualExistsParameter(text="Test")
        )
        await test.test(mock_visual_context)

        assert call_order == ["screenshot", "find_text"]

    @pytest.mark.asyncio
    async def test_visual_value_error_exception(self, mock_visual_context):
        """Test ValueError exception handling."""
        mock_visual_context.cv.find_text = AsyncMock(side_effect=ValueError("Invalid search params"))

        test = VisualExists(
            name="test_value_error",
            parameter=VisualExistsParameter(text="Test")
        )
        result = await test.test(mock_visual_context)

        assert_test_execution_error(result)
        assert "Error in testfunction 'visual.exists'" in result.details[0]

    @pytest.mark.asyncio
    async def test_visual_relative_image_path_resolution(self, mock_visual_context, tmp_path):
        """Test that relative image paths are resolved using playbook_dir."""
        # Create image in playbook directory
        playbook_dir = tmp_path / "playbooks"
        playbook_dir.mkdir()
        image_file = playbook_dir / "relative_icon.png"
        image_file.write_bytes(b"fake_image")

        mock_visual_context.playbook_dir = playbook_dir
        mock_visual_context.cv.find_icon = AsyncMock(return_value=[(50, 50)])

        test = VisualExists(
            name="test_relative_path",
            parameter=VisualExistsParameter(image="relative_icon.png")
        )
        result = await test.test(mock_visual_context)

        assert_test_success(result)
        # Verify find_icon was called with resolved path
        call_args = mock_visual_context.cv.find_icon.call_args
        assert call_args[0][0] == playbook_dir / "relative_icon.png"

    @pytest.mark.asyncio
    async def test_visual_all_count_tests_with_window_param(self, mock_visual_context, tmp_path):
        """Test that window parameter works for all count tests."""
        mock_visual_context.cv.find_text = AsyncMock(return_value=[(10, 20), (30, 40)])

        # Test VisualCountEquals
        test_equals = VisualCountEquals(
            name="test_equals_window",
            parameter=VisualCountEqualsParameter(text="Item", n=2, window="TestWindow")
        )
        result = await test_equals.test(mock_visual_context)
        assert_test_success(result)
        assert mock_visual_context.screenshot.take.call_args[1]["window"] == "TestWindow"

        # Reset mock
        mock_visual_context.screenshot.take.reset_mock()

        # Test VisualCountMin
        test_min = VisualCountMin(
            name="test_min_window",
            parameter=VisualCountMinParameter(text="Item", min=1, window="MinWindow")
        )
        result = await test_min.test(mock_visual_context)
        assert_test_success(result)
        assert mock_visual_context.screenshot.take.call_args[1]["window"] == "MinWindow"

        # Reset mock
        mock_visual_context.screenshot.take.reset_mock()

        # Test VisualCountMax
        test_max = VisualCountMax(
            name="test_max_window",
            parameter=VisualCountMaxParameter(text="Item", max=5, window="MaxWindow")
        )
        result = await test_max.test(mock_visual_context)
        assert_test_success(result)
        assert mock_visual_context.screenshot.take.call_args[1]["window"] == "MaxWindow"

    @pytest.mark.asyncio
    async def test_visual_testname_class_variables(self):
        """Verify that testname class variables are correctly set."""
        assert VisualExists.testname == 'visual.exists'
        assert VisualNotExists.testname == 'visual.not_exists'
        assert VisualCountEquals.testname == 'visual.count_equals'
        assert VisualCountMin.testname == 'visual.count_min'
        assert VisualCountMax.testname == 'visual.count_max'

    @pytest.mark.asyncio
    async def test_visual_testdescription_class_variables(self):
        """Verify that testdescription class variables are correctly set."""
        assert VisualExists.testdescription == 'Check if text or image is visible on screen'
        assert VisualNotExists.testdescription == 'Check if text or image is NOT visible on screen'
        assert VisualCountEquals.testdescription == 'Check if text or image appears exactly N times on screen'
        assert VisualCountMin.testdescription == 'Check if text or image appears at least N times on screen'
        assert VisualCountMax.testdescription == 'Check if text or image appears at most N times on screen'

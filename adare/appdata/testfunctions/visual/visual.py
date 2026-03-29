"""
Visual test functions for ADARE.

These test functions execute on the HOST (not VM) and use the CV server
to perform visual analysis of screenshots for text/icon detection.
"""

import attrs
from pathlib import Path
from typing import ClassVar, Optional
import logging

from adarelib.testset.basictest import BasicTest, Parameter, HostModeCategory
from adarelib.event.event import TestResult

log = logging.getLogger(__name__)


# =============================================================================
# Parameter Classes
# =============================================================================

@attrs.define
class VisualExistsParameter(Parameter):
    """Parameters for visual existence checks."""
    text: Optional[str] = None
    image: Optional[str] = None
    window: Optional[str] = None


@attrs.define
class VisualCountParameter(Parameter):
    """Parameters for visual count checks."""
    text: Optional[str] = None
    image: Optional[str] = None
    window: Optional[str] = None
    n: Optional[int] = None  # For count_equals
    min: Optional[int] = None  # For count_min
    max: Optional[int] = None  # For count_max


# =============================================================================
# Visual Test Functions
# =============================================================================

@attrs.define
class VisualExists(BasicTest):
    """Test if text or image is visible on screen."""

    testname: ClassVar[str] = 'visual.exists'
    testdescription: ClassVar[str] = 'Check if text or image is visible on screen'
    execute_on_host: ClassVar[bool] = True
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.HOST_NATIVE

    name: str
    parameter: VisualExistsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    async def test(self, context) -> TestResult:
        """
        Execute visual existence check.

        Args:
            context: HostTestContext with cv, screenshot, vm_file services

        Returns:
            TestResult indicating success or failure
        """
        try:
            # Validate parameters
            if not self.parameter.text and not self.parameter.image:
                return TestResult.execution_error(
                    ValueError("Either text or image parameter required"),
                    "Invalid parameters"
                )

            # Take screenshot
            screenshot = await context.screenshot.take(window=self.parameter.window)

            # Search for visual element
            if self.parameter.text:
                log.debug(f"Visual test '{self.name}': Searching for text '{self.parameter.text}'")
                locations = await context.cv.find_text(self.parameter.text, screenshot)
                target_desc = f"text '{self.parameter.text}'"
            else:
                # Image search
                image_path = Path(self.parameter.image)
                if not image_path.is_absolute():
                    image_path = context.playbook_dir / image_path

                log.debug(f"Visual test '{self.name}': Searching for image '{image_path.name}'")
                locations = await context.cv.find_icon(image_path, screenshot)
                target_desc = f"image '{self.parameter.image}'"

            # Check result
            if locations:
                log.debug(f"Visual test '{self.name}': Found {len(locations)} matches")
                return TestResult.success()
            else:
                log.debug(f"Visual test '{self.name}': No matches found")
                return TestResult.failed([f"Visual element not found: {target_desc}"])

        except FileNotFoundError as e:
            return TestResult.execution_error(e, f"Image file not found: {self.parameter.image}")
        except ValueError as e:
            return TestResult.execution_error(e, str(e))
        except Exception as e:
            log.error(f"Visual test '{self.name}' failed with error: {e}", exc_info=True)
            return TestResult.execution_error(e, f"Visual test execution failed: {e}")


@attrs.define
class VisualNotExists(BasicTest):
    """Test if text or image is NOT visible on screen."""

    testname: ClassVar[str] = 'visual.not_exists'
    testdescription: ClassVar[str] = 'Check if text or image is NOT visible on screen'
    execute_on_host: ClassVar[bool] = True
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.HOST_NATIVE

    name: str
    parameter: VisualExistsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    async def test(self, context) -> TestResult:
        """
        Execute visual non-existence check.

        Args:
            context: HostTestContext with cv, screenshot, vm_file services

        Returns:
            TestResult indicating success or failure
        """
        try:
            # Validate parameters
            if not self.parameter.text and not self.parameter.image:
                return TestResult.execution_error(
                    ValueError("Either text or image parameter required"),
                    "Invalid parameters"
                )

            # Take screenshot
            screenshot = await context.screenshot.take(window=self.parameter.window)

            # Search for visual element
            if self.parameter.text:
                log.debug(f"Visual test '{self.name}': Checking text '{self.parameter.text}' is not present")
                locations = await context.cv.find_text(self.parameter.text, screenshot)
                target_desc = f"text '{self.parameter.text}'"
            else:
                # Image search
                image_path = Path(self.parameter.image)
                if not image_path.is_absolute():
                    image_path = context.playbook_dir / image_path

                log.debug(f"Visual test '{self.name}': Checking image '{image_path.name}' is not present")
                locations = await context.cv.find_icon(image_path, screenshot)
                target_desc = f"image '{self.parameter.image}'"

            # Check result (inverted logic)
            if not locations:
                log.debug(f"Visual test '{self.name}': Confirmed element not present")
                return TestResult.success()
            else:
                log.debug(f"Visual test '{self.name}': Found {len(locations)} unexpected matches")
                return TestResult.failed([f"Visual element should not exist but was found: {target_desc}"])

        except FileNotFoundError as e:
            return TestResult.execution_error(e, f"Image file not found: {self.parameter.image}")
        except ValueError as e:
            return TestResult.execution_error(e, str(e))
        except Exception as e:
            log.error(f"Visual test '{self.name}' failed with error: {e}", exc_info=True)
            return TestResult.execution_error(e, f"Visual test execution failed: {e}")


@attrs.define
class VisualCountEquals(BasicTest):
    """Test if text or image appears exactly N times on screen."""

    testname: ClassVar[str] = 'visual.count_equals'
    testdescription: ClassVar[str] = 'Check if text or image appears exactly N times on screen'
    execute_on_host: ClassVar[bool] = True
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.HOST_NATIVE

    name: str
    parameter: VisualCountParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    async def test(self, context) -> TestResult:
        """
        Execute visual count equals check.

        Args:
            context: HostTestContext with cv, screenshot, vm_file services

        Returns:
            TestResult indicating success or failure
        """
        try:
            # Validate parameters
            if not self.parameter.text and not self.parameter.image:
                return TestResult.execution_error(
                    ValueError("Either text or image parameter required"),
                    "Invalid parameters"
                )
            if self.parameter.n is None:
                return TestResult.execution_error(
                    ValueError("Parameter 'n' required for count_equals test"),
                    "Invalid parameters"
                )

            # Take screenshot
            screenshot = await context.screenshot.take(window=self.parameter.window)

            # Search for visual element
            if self.parameter.text:
                log.debug(f"Visual test '{self.name}': Counting text '{self.parameter.text}'")
                locations = await context.cv.find_text(self.parameter.text, screenshot)
                target_desc = f"text '{self.parameter.text}'"
            else:
                # Image search
                image_path = Path(self.parameter.image)
                if not image_path.is_absolute():
                    image_path = context.playbook_dir / image_path

                log.debug(f"Visual test '{self.name}': Counting image '{image_path.name}'")
                locations = await context.cv.find_icon(image_path, screenshot)
                target_desc = f"image '{self.parameter.image}'"

            # Check count
            actual_count = len(locations)
            expected_count = self.parameter.n

            log.debug(f"Visual test '{self.name}': Expected {expected_count}, found {actual_count}")

            if actual_count == expected_count:
                return TestResult.success()
            else:
                return TestResult.failed([
                    f"Visual element count mismatch for {target_desc}: "
                    f"expected {expected_count}, found {actual_count}"
                ])

        except FileNotFoundError as e:
            return TestResult.execution_error(e, f"Image file not found: {self.parameter.image}")
        except ValueError as e:
            return TestResult.execution_error(e, str(e))
        except Exception as e:
            log.error(f"Visual test '{self.name}' failed with error: {e}", exc_info=True)
            return TestResult.execution_error(e, f"Visual test execution failed: {e}")


@attrs.define
class VisualCountMin(BasicTest):
    """Test if text or image appears at least N times on screen."""

    testname: ClassVar[str] = 'visual.count_min'
    testdescription: ClassVar[str] = 'Check if text or image appears at least N times on screen'
    execute_on_host: ClassVar[bool] = True
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.HOST_NATIVE

    name: str
    parameter: VisualCountParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    async def test(self, context) -> TestResult:
        """
        Execute visual minimum count check.

        Args:
            context: HostTestContext with cv, screenshot, vm_file services

        Returns:
            TestResult indicating success or failure
        """
        try:
            # Validate parameters
            if not self.parameter.text and not self.parameter.image:
                return TestResult.execution_error(
                    ValueError("Either text or image parameter required"),
                    "Invalid parameters"
                )
            if self.parameter.min is None:
                return TestResult.execution_error(
                    ValueError("Parameter 'min' required for count_min test"),
                    "Invalid parameters"
                )

            # Take screenshot
            screenshot = await context.screenshot.take(window=self.parameter.window)

            # Search for visual element
            if self.parameter.text:
                log.debug(f"Visual test '{self.name}': Counting text '{self.parameter.text}'")
                locations = await context.cv.find_text(self.parameter.text, screenshot)
                target_desc = f"text '{self.parameter.text}'"
            else:
                # Image search
                image_path = Path(self.parameter.image)
                if not image_path.is_absolute():
                    image_path = context.playbook_dir / image_path

                log.debug(f"Visual test '{self.name}': Counting image '{image_path.name}'")
                locations = await context.cv.find_icon(image_path, screenshot)
                target_desc = f"image '{self.parameter.image}'"

            # Check minimum count
            actual_count = len(locations)
            min_count = self.parameter.min

            log.debug(f"Visual test '{self.name}': Expected >= {min_count}, found {actual_count}")

            if actual_count >= min_count:
                return TestResult.success()
            else:
                return TestResult.failed([
                    f"Visual element count below minimum for {target_desc}: "
                    f"expected >= {min_count}, found {actual_count}"
                ])

        except FileNotFoundError as e:
            return TestResult.execution_error(e, f"Image file not found: {self.parameter.image}")
        except ValueError as e:
            return TestResult.execution_error(e, str(e))
        except Exception as e:
            log.error(f"Visual test '{self.name}' failed with error: {e}", exc_info=True)
            return TestResult.execution_error(e, f"Visual test execution failed: {e}")


@attrs.define
class VisualCountMax(BasicTest):
    """Test if text or image appears at most N times on screen."""

    testname: ClassVar[str] = 'visual.count_max'
    testdescription: ClassVar[str] = 'Check if text or image appears at most N times on screen'
    execute_on_host: ClassVar[bool] = True
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.HOST_NATIVE

    name: str
    parameter: VisualCountParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    async def test(self, context) -> TestResult:
        """
        Execute visual maximum count check.

        Args:
            context: HostTestContext with cv, screenshot, vm_file services

        Returns:
            TestResult indicating success or failure
        """
        try:
            # Validate parameters
            if not self.parameter.text and not self.parameter.image:
                return TestResult.execution_error(
                    ValueError("Either text or image parameter required"),
                    "Invalid parameters"
                )
            if self.parameter.max is None:
                return TestResult.execution_error(
                    ValueError("Parameter 'max' required for count_max test"),
                    "Invalid parameters"
                )

            # Take screenshot
            screenshot = await context.screenshot.take(window=self.parameter.window)

            # Search for visual element
            if self.parameter.text:
                log.debug(f"Visual test '{self.name}': Counting text '{self.parameter.text}'")
                locations = await context.cv.find_text(self.parameter.text, screenshot)
                target_desc = f"text '{self.parameter.text}'"
            else:
                # Image search
                image_path = Path(self.parameter.image)
                if not image_path.is_absolute():
                    image_path = context.playbook_dir / image_path

                log.debug(f"Visual test '{self.name}': Counting image '{image_path.name}'")
                locations = await context.cv.find_icon(image_path, screenshot)
                target_desc = f"image '{self.parameter.image}'"

            # Check maximum count
            actual_count = len(locations)
            max_count = self.parameter.max

            log.debug(f"Visual test '{self.name}': Expected <= {max_count}, found {actual_count}")

            if actual_count <= max_count:
                return TestResult.success()
            else:
                return TestResult.failed([
                    f"Visual element count exceeds maximum for {target_desc}: "
                    f"expected <= {max_count}, found {actual_count}"
                ])

        except FileNotFoundError as e:
            return TestResult.execution_error(e, f"Image file not found: {self.parameter.image}")
        except ValueError as e:
            return TestResult.execution_error(e, str(e))
        except Exception as e:
            log.error(f"Visual test '{self.name}' failed with error: {e}", exc_info=True)
            return TestResult.execution_error(e, f"Visual test execution failed: {e}")
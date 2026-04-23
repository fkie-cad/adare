
import sys
from pathlib import Path

import pytest

# Add paths for imports
# Current file is in tests/unit/types/test_playbook_parsing.py
# PROJECT_ROOT is adare/adare
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ADARELIB_ROOT = PROJECT_ROOT.parent / "adarelib"

# Add to sys.path if not already there
if str(ADARELIB_ROOT) not in sys.path:
    sys.path.insert(0, str(ADARELIB_ROOT))

from adare.types.playbook import PixelChangeConstraint, SkipOptions, Target, WaitCondition, WaitUntilAction


class TestPixelChangeConstraintParsing:
    """Tests for parsing PixelChangeConstraint and WaitUntilAction."""

    def test_pixel_change_constraint_init(self):
        """Test direct initialization of PixelChangeConstraint with idle."""
        constraint = PixelChangeConstraint(above=1.0, idle=2.5)
        assert constraint.above == 1.0
        assert constraint.idle == 2.5
        assert constraint.strategy == 'once'  # Default

    def test_pixel_change_constraint_all_fields(self):
        """Test initialization with all fields."""
        constraint = PixelChangeConstraint(
            above=1.0,
            below=0.5,
            strategy='continuous',
            idle=5.0
        )
        assert constraint.above == 1.0
        assert constraint.below == 0.5
        assert constraint.strategy == 'continuous'
        assert constraint.idle == 5.0

    def test_invalid_strategy_raises_error(self):
        """Test that invalid strategy raises ValueError."""
        with pytest.raises(ValueError, match="PixelChangeConstraint.strategy must be one of"):
            PixelChangeConstraint(strategy='invalid')

class TestWaitUntilActionParsing:
    """Tests for WaitUntilAction parsing with nested constraints."""

    def test_wait_until_with_idle_constraint(self):
        """Test initializing WaitUntilAction with a constraint containing idle."""
        target = Target(text="something")
        condition = WaitCondition(exists=target)

        pixel_constraint = PixelChangeConstraint(above=1.0, idle=2.0)
        skip_options = SkipOptions(pixel_change=pixel_constraint)

        action = WaitUntilAction(
            condition=condition,
            skip=skip_options
        )

        assert action.skip is not None
        assert action.skip.pixel_change is not None
        assert action.skip.pixel_change.idle == 2.0
        assert action.skip.pixel_change.above == 1.0

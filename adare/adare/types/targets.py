"""How a playbook action finds something on screen: targets, match settings and selection strategies."""

from __future__ import annotations

import attrs


# Target selection strategies
@attrs.define
class SweepStrategy:
    """Select the nth match when scanning left-to-right, top-to-bottom."""

    index: int = 1  # 1-based index (1 = first, 2 = second, etc.)


@attrs.define
class BestConfidenceStrategy:
    """Select match with highest confidence score."""

    pass


@attrs.define
class ClosestToStrategy:
    """Select match closest to coordinates or target reference.

    Supports three modes:
    1. Fixed coordinates: x, y specified
    2. Text reference: text specified
    3. Image reference: image specified

    Optional max_distance enables region-based search optimization.
    """

    # Mode 1: Fixed coordinates (existing - backwards compatible)
    x: int | None = None
    y: int | None = None

    # Mode 2: Text reference (new)
    text: str | None = None

    # Mode 3: Image reference (new)
    image: str | None = None

    # Optional distance limit (new)
    max_distance: int | None = None  # pixels

    def __attrs_post_init__(self):
        """Validate that exactly one mode is specified."""
        modes_set = sum(
            [
                self.x is not None and self.y is not None,  # coordinates mode
                self.text is not None,  # text reference mode
                self.image is not None,  # image reference mode
            ]
        )

        if modes_set != 1:
            raise ValueError(
                "ClosestToStrategy must specify exactly one of: (x, y) coordinates, text reference, or image reference"
            )

        # Validate x,y together
        if (self.x is None) != (self.y is None):
            raise ValueError("ClosestToStrategy: x and y must both be specified or both be None")

        # Validate max_distance
        if self.max_distance is not None and self.max_distance <= 0:
            raise ValueError(f"ClosestToStrategy: max_distance must be positive, got {self.max_distance}")


@attrs.define
class TopLeftStrategy:
    """Select topmost-leftmost match."""

    pass


@attrs.define
class TopRightStrategy:
    """Select topmost-rightmost match."""

    pass


@attrs.define
class BottomLeftStrategy:
    """Select bottommost-leftmost match."""

    pass


@attrs.define
class BottomRightStrategy:
    """Select bottommost-rightmost match."""

    pass


@attrs.define
class LargestStrategy:
    """Select match with largest bounding box area."""

    pass


@attrs.define
class SmallestStrategy:
    """Select match with smallest bounding box area."""

    pass


TargetStrategyType = (
    SweepStrategy
    | BestConfidenceStrategy
    | ClosestToStrategy
    | TopLeftStrategy
    | TopRightStrategy
    | BottomLeftStrategy
    | BottomRightStrategy
    | LargestStrategy
    | SmallestStrategy
)


@attrs.define
class Offset:
    x: int = 0
    y: int = 0
    base: str = 'center'  # center, top-left, top-right, bottom-left, bottom-right, center-left, center-right, top-center, bottom-center

    def __attrs_post_init__(self):
        valid_bases = {
            'center',
            'top-left',
            'top-right',
            'bottom-left',
            'bottom-right',
            'center-left',
            'center-right',
            'top-center',
            'bottom-center',
        }
        if self.base not in valid_bases:
            raise ValueError(f"Offset.base must be one of {valid_bases}, got '{self.base}'")


@attrs.define
class TextMatchConfig:
    """Configuration for text matching behavior.

    Supports multiple matching modes:
    - substring: Simple case-insensitive substring matching (default)
    - regex: Regular expression pattern matching
    - fuzzy: Fuzzy matching for OCR inaccuracies
    - regex_fuzzy: Combined regex + fuzzy matching
    """

    mode: str = 'substring'  # 'substring', 'regex', 'fuzzy', 'regex_fuzzy'
    flags: list[str] | None = None  # Regex flags: IGNORECASE, MULTILINE, DOTALL, VERBOSE
    allow_missing_chars: bool | str | list[str] | None = (
        None  # True = any char, "." = only dots, [".", ","] = specific chars
    )
    max_missing: int | None = None  # Max missing chars allowed (requires allow_missing_chars)
    min_similarity: float | None = None  # Minimum similarity ratio 0.0-1.0
    case_sensitive: bool = False  # Enable case-sensitive matching

    def __attrs_post_init__(self):
        """Validate configuration fields."""
        # Validate mode
        valid_modes = {'substring', 'regex', 'fuzzy', 'regex_fuzzy'}
        if self.mode not in valid_modes:
            raise ValueError(f"TextMatchConfig.mode must be one of {valid_modes}, got '{self.mode}'")

        # Validate min_similarity range
        if self.min_similarity is not None and not (0.0 <= self.min_similarity <= 1.0):
            raise ValueError(f"TextMatchConfig.min_similarity must be between 0.0 and 1.0, got {self.min_similarity}")

        # Validate max_missing
        if self.max_missing is not None and self.max_missing < 0:
            raise ValueError(f"TextMatchConfig.max_missing must be >= 0, got {self.max_missing}")

        # Fuzzy mode requires either allow_missing_chars or min_similarity
        if self.mode in ('fuzzy', 'regex_fuzzy') and self.allow_missing_chars is None and self.min_similarity is None:
            raise ValueError(
                f"TextMatchConfig with mode='{self.mode}' requires either "
                f"allow_missing_chars or min_similarity to be specified"
            )

        # Validate regex flags
        if self.flags:
            valid_flags = {'IGNORECASE', 'MULTILINE', 'DOTALL', 'VERBOSE'}
            invalid_flags = set(self.flags) - valid_flags
            if invalid_flags:
                raise ValueError(
                    f"TextMatchConfig.flags contains invalid values: {invalid_flags}. Valid flags: {valid_flags}"
                )


@attrs.define
class Target:
    image: str | None = None
    text: str | None = None
    icon: str | None = None  # Windows icon-library term (extracted from target at runtime)
    text_match: TextMatchConfig | None = None  # Text matching configuration
    position: list[int] | None = None
    strategy: TargetStrategyType | None = None
    offset: Offset | None = None
    use_cache: bool | None = None  # If False, forces a fresh detection even when the
    # immediately-preceding target resolution would
    # otherwise be reused. Default (None/True): auto-reuse.
    min_margin: float | None = None  # Image targets: accept the selected match only if its confidence beats the
    # best other candidate by at least this much (0.0-1.0). None = no margin check.

    def __attrs_post_init__(self):
        if self.min_margin is not None and not (0.0 <= self.min_margin <= 1.0):
            raise ValueError(f"Target.min_margin must be between 0.0 and 1.0, got {self.min_margin}")


@attrs.define
class ExistsCondition:
    text: str | None = None
    image: str | None = None


@attrs.define
class NotExistsCondition:
    text: str | None = None
    image: str | None = None

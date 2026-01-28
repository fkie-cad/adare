"""
Tests for parse_indices_with_bounds function in CLI dev module.
"""

import pytest
from adare.cli.dev import parse_indices_with_bounds


class TestParseIndicesWithBounds:
    """Test the parse_indices_with_bounds function with S/E support."""

    def test_numeric_single_index(self):
        """Test single numeric index."""
        result = parse_indices_with_bounds("5", 10)
        assert result == [5]

    def test_numeric_range(self):
        """Test numeric range."""
        result = parse_indices_with_bounds("3-7", 10)
        assert result == [3, 4, 5, 6, 7]

    def test_numeric_multiple_ranges(self):
        """Test multiple numeric ranges."""
        result = parse_indices_with_bounds("1-3,5,7-9", 10)
        assert result == [1, 2, 3, 5, 7, 8, 9]

    def test_start_index_s(self):
        """Test S (start) index."""
        result = parse_indices_with_bounds("S", 10)
        assert result == [1]

    def test_end_index_e(self):
        """Test E (end) index."""
        result = parse_indices_with_bounds("E", 10)
        assert result == [10]

    def test_start_to_number_range(self):
        """Test S-5 range."""
        result = parse_indices_with_bounds("S-5", 10)
        assert result == [1, 2, 3, 4, 5]

    def test_number_to_end_range(self):
        """Test 7-E range."""
        result = parse_indices_with_bounds("7-E", 10)
        assert result == [7, 8, 9, 10]

    def test_start_to_end_range(self):
        """Test S-E range (all actions)."""
        result = parse_indices_with_bounds("S-E", 10)
        assert result == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    def test_mixed_s_e_numeric(self):
        """Test mixed S, E, and numeric indices."""
        result = parse_indices_with_bounds("S-3,5,8-E", 10)
        assert result == [1, 2, 3, 5, 8, 9, 10]

    def test_case_insensitive(self):
        """Test case-insensitive S and E."""
        result_lower = parse_indices_with_bounds("s-5,7,9-e", 10)
        result_upper = parse_indices_with_bounds("S-5,7,9-E", 10)
        assert result_lower == result_upper == [1, 2, 3, 4, 5, 7, 9, 10]

    def test_duplicate_indices_removed(self):
        """Test that duplicate indices are removed."""
        result = parse_indices_with_bounds("1-3,2-4", 10)
        assert result == [1, 2, 3, 4]

    def test_out_of_bounds_low(self):
        """Test index below 1 raises ValueError."""
        with pytest.raises(ValueError, match="Index 0 out of bounds"):
            parse_indices_with_bounds("0", 10)

    def test_out_of_bounds_high(self):
        """Test index above total_actions raises ValueError."""
        with pytest.raises(ValueError, match="Index 15 out of bounds"):
            parse_indices_with_bounds("15", 10)

    def test_range_out_of_bounds(self):
        """Test range extending beyond bounds raises ValueError."""
        with pytest.raises(ValueError, match="Index 15 out of bounds"):
            parse_indices_with_bounds("5-15", 10)

    def test_invalid_range_format(self):
        """Test invalid range format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid range format"):
            parse_indices_with_bounds("1-2-3", 10)

    def test_backward_range(self):
        """Test backward range (end < start) raises ValueError."""
        with pytest.raises(ValueError, match="Invalid range.*start.*>.*end"):
            parse_indices_with_bounds("5-3", 10)

    def test_backward_range_with_e(self):
        """Test E-S raises ValueError (backward range after substitution)."""
        with pytest.raises(ValueError, match="Invalid range.*start.*>.*end"):
            parse_indices_with_bounds("E-S", 10)

    def test_invalid_characters(self):
        """Test invalid characters raise ValueError."""
        with pytest.raises(ValueError):
            parse_indices_with_bounds("1,a,3", 10)

    def test_whitespace_handling(self):
        """Test that whitespace is handled correctly."""
        result = parse_indices_with_bounds(" 1 - 3 , 5 , 7 - 9 ", 10)
        assert result == [1, 2, 3, 5, 7, 8, 9]

    def test_single_action_playbook(self):
        """Test with single action playbook."""
        result = parse_indices_with_bounds("S-E", 1)
        assert result == [1]

    def test_large_playbook(self):
        """Test with large playbook."""
        result = parse_indices_with_bounds("S-5,50,95-E", 100)
        assert result == [1, 2, 3, 4, 5, 50, 95, 96, 97, 98, 99, 100]

    def test_empty_parts_ignored(self):
        """Test that empty parts (e.g., trailing commas) are ignored."""
        result = parse_indices_with_bounds("1,2,,3,", 10)
        assert result == [1, 2, 3]

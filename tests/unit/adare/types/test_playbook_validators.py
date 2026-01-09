"""Unit tests for adare.types.playbook_validators module.

Comprehensive tests for playbook validation framework including:
- ValidationError and ValidationResult dataclasses
- VariableUsageValidator for extracting variable references
- FilterValidator for validating filter syntax
- DuplicateVariableValidator for detecting duplicate definitions
- VariableDefinitionValidator for checking variable definitions
- validate_playbook() orchestration function
"""

import pytest
from unittest.mock import MagicMock, patch
from typing import List, Dict, Any, Optional

from adare.types.playbook_validators import (
    ValidationError,
    ValidationResult,
    PlaybookValidator,
    VariableUsageValidator,
    FilterValidator,
    DuplicateVariableValidator,
    VariableDefinitionValidator,
    validate_playbook,
)
from adare.types.playbook import (
    Playbook,
    Settings,
    Target,
    ClickAction,
    DragAction,
    KeyboardAction,
    CommandAction,
    CaptureSpec,
    SaveTimestampAction,
    PullAction,
    ActionTestAction,
    GotoAction,
    BlockAction,
    WaitUntilAction,
    WaitCondition,
    StopAction,
    ContinueAction,
    VariableCondition,
    IdleAction,
)


# === Helper Functions for Creating Mock Objects ===

def create_mock_variable_registry(variables: Dict[str, str]) -> MagicMock:
    """Create a mock VariableRegistry with specified variables and types.

    Args:
        variables: Dict mapping variable name to type string (e.g., 'STRING', 'TIMESTAMP')
    """
    mock_registry = MagicMock()
    mock_variables = {}

    for var_name, var_type in variables.items():
        mock_var = MagicMock()
        mock_var.type.name = var_type
        mock_variables[var_name] = mock_var

    mock_registry.variables = mock_variables
    return mock_registry


def create_playbook(
    actions: List = None,
    variables: Dict[str, str] = None,
    settings: Settings = None
) -> Playbook:
    """Create a Playbook instance for testing.

    Args:
        actions: List of action objects
        variables: Dict mapping variable name to type for mock registry
        settings: Optional Settings object
    """
    if actions is None:
        actions = []

    mock_vars = None
    if variables:
        mock_vars = create_mock_variable_registry(variables)

    return Playbook(
        actions=actions,
        settings=settings or Settings(),
        variables=mock_vars,
        tests=[]
    )


# === ValidationError Tests ===

class TestValidationError:
    """Tests for ValidationError dataclass."""

    def test_basic_error_message(self):
        """ValidationError should store basic message."""
        error = ValidationError(message="Test error message")

        assert error.message == "Test error message"
        assert error.action_index is None
        assert error.action_type is None
        assert error.field_name is None
        assert error.variable_name is None

    def test_full_error_context(self):
        """ValidationError should store all context fields."""
        error = ValidationError(
            message="Variable not defined",
            action_index=5,
            action_type="ClickAction",
            field_name="target.text",
            variable_name="my_var"
        )

        assert error.message == "Variable not defined"
        assert error.action_index == 5
        assert error.action_type == "ClickAction"
        assert error.field_name == "target.text"
        assert error.variable_name == "my_var"

    def test_str_representation_basic(self):
        """__str__ should show basic message."""
        error = ValidationError(message="Test error")

        result = str(error)
        assert "Validation Error: Test error" in result

    def test_str_representation_with_action_index(self):
        """__str__ should include action index when provided."""
        error = ValidationError(
            message="Error occurred",
            action_index=3
        )

        result = str(error)
        assert "at action index 3" in result

    def test_str_representation_with_action_type(self):
        """__str__ should include action type when provided."""
        error = ValidationError(
            message="Error occurred",
            action_type="CommandAction"
        )

        result = str(error)
        assert "(CommandAction)" in result

    def test_str_representation_with_field_name(self):
        """__str__ should include field name when provided."""
        error = ValidationError(
            message="Error occurred",
            field_name="target.text"
        )

        result = str(error)
        assert "in field 'target.text'" in result

    def test_str_representation_full(self):
        """__str__ should include all context information."""
        error = ValidationError(
            message="Invalid variable",
            action_index=2,
            action_type="KeyboardAction",
            field_name="text"
        )

        result = str(error)
        assert "Validation Error: Invalid variable" in result
        assert "at action index 2" in result
        assert "(KeyboardAction)" in result
        assert "in field 'text'" in result


# === ValidationResult Tests ===

class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_empty_result_is_valid(self):
        """Empty ValidationResult should be valid."""
        result = ValidationResult()

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 0

    def test_add_error_makes_invalid(self):
        """Adding an error should make result invalid."""
        result = ValidationResult()
        result.add_error("Test error")

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert result.errors[0].message == "Test error"

    def test_add_error_with_full_context(self):
        """add_error should create ValidationError with all context."""
        result = ValidationResult()
        result.add_error(
            message="Variable missing",
            action_index=5,
            action_type="ClickAction",
            field_name="target.text",
            variable_name="my_var"
        )

        assert len(result.errors) == 1
        error = result.errors[0]
        assert error.message == "Variable missing"
        assert error.action_index == 5
        assert error.action_type == "ClickAction"
        assert error.field_name == "target.text"
        assert error.variable_name == "my_var"

    def test_add_multiple_errors(self):
        """Multiple errors can be added to result."""
        result = ValidationResult()
        result.add_error("Error 1")
        result.add_error("Error 2")
        result.add_error("Error 3")

        assert result.is_valid is False
        assert len(result.errors) == 3
        assert result.errors[0].message == "Error 1"
        assert result.errors[1].message == "Error 2"
        assert result.errors[2].message == "Error 3"

    def test_add_warning(self):
        """Adding warnings should not affect validity."""
        result = ValidationResult()
        result.add_warning("This is a warning")

        assert result.is_valid is True
        assert len(result.warnings) == 1
        assert result.warnings[0] == "This is a warning"

    def test_warnings_with_errors(self):
        """Warnings and errors can coexist."""
        result = ValidationResult()
        result.add_warning("Warning 1")
        result.add_error("Error 1")
        result.add_warning("Warning 2")

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert len(result.warnings) == 2

    def test_merge_results(self):
        """merge() should combine errors and warnings from another result."""
        result1 = ValidationResult()
        result1.add_error("Error 1")
        result1.add_warning("Warning 1")

        result2 = ValidationResult()
        result2.add_error("Error 2")
        result2.add_warning("Warning 2")

        result1.merge(result2)

        assert len(result1.errors) == 2
        assert len(result1.warnings) == 2
        assert result1.errors[0].message == "Error 1"
        assert result1.errors[1].message == "Error 2"
        assert result1.warnings[0] == "Warning 1"
        assert result1.warnings[1] == "Warning 2"

    def test_merge_empty_result(self):
        """Merging empty result should not change anything."""
        result1 = ValidationResult()
        result1.add_error("Error 1")

        result2 = ValidationResult()
        result1.merge(result2)

        assert len(result1.errors) == 1

    def test_merge_into_empty_result(self):
        """Merging into empty result should add all items."""
        result1 = ValidationResult()

        result2 = ValidationResult()
        result2.add_error("Error 1")
        result2.add_warning("Warning 1")

        result1.merge(result2)

        assert len(result1.errors) == 1
        assert len(result1.warnings) == 1


# === VariableUsageValidator Tests ===

class TestVariableUsageValidator:
    """Tests for VariableUsageValidator."""

    def test_variable_pattern_simple(self):
        """VARIABLE_PATTERN should match simple variable references."""
        pattern = VariableUsageValidator.VARIABLE_PATTERN

        matches = pattern.findall("{{my_variable}}")
        assert matches == ["my_variable"]

    def test_variable_pattern_with_spaces(self):
        """VARIABLE_PATTERN should match variables with surrounding spaces."""
        pattern = VariableUsageValidator.VARIABLE_PATTERN

        matches = pattern.findall("{{ my_variable }}")
        assert matches == ["my_variable"]

    def test_variable_pattern_with_filter(self):
        """VARIABLE_PATTERN should extract variable name with filters."""
        pattern = VariableUsageValidator.VARIABLE_PATTERN

        matches = pattern.findall("{{timestamp | format('%Y-%m-%d')}}")
        assert matches == ["timestamp"]

    def test_variable_pattern_multiple_filters(self):
        """VARIABLE_PATTERN should handle multiple filters."""
        pattern = VariableUsageValidator.VARIABLE_PATTERN

        matches = pattern.findall("{{var | filter1 | filter2}}")
        assert matches == ["var"]

    def test_variable_pattern_multiple_variables(self):
        """VARIABLE_PATTERN should find all variables in string."""
        pattern = VariableUsageValidator.VARIABLE_PATTERN

        text = "Path: {{base_path}}/{{subdir}}/{{filename}}"
        matches = pattern.findall(text)
        assert matches == ["base_path", "subdir", "filename"]

    @pytest.mark.parametrize("text,expected", [
        ("{{var}}", ["var"]),
        ("{{ var }}", ["var"]),
        ("{{  var  }}", ["var"]),
        ("{{var|filter}}", ["var"]),
        ("{{var | filter}}", ["var"]),
        ("{{ var | filter }}", ["var"]),
        ("{{var_name123}}", ["var_name123"]),
        ("{{_underscore}}", ["_underscore"]),
    ])
    def test_variable_pattern_parametrized(self, text, expected):
        """VARIABLE_PATTERN should correctly extract variable names."""
        pattern = VariableUsageValidator.VARIABLE_PATTERN
        matches = pattern.findall(text)
        assert matches == expected

    def test_validate_returns_empty_result(self):
        """validate() should return empty result (no errors from this validator)."""
        validator = VariableUsageValidator()
        playbook = create_playbook(actions=[])

        result = validator.validate(playbook)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_extract_from_click_action_target_text(self):
        """Should extract variables from ClickAction target.text."""
        validator = VariableUsageValidator()

        click = ClickAction(
            target=Target(text="{{button_label}}")
        )
        playbook = create_playbook(actions=[click])

        validator.validate(playbook)

        assert "button_label" in validator.variable_references
        refs = validator.variable_references["button_label"]
        assert len(refs) == 1
        assert refs[0][0] == 0  # action_index
        assert refs[0][1] == "ClickAction"  # action_type
        assert refs[0][2] == "target.text"  # field_name

    def test_extract_from_click_action_target_image(self):
        """Should extract variables from ClickAction target.image."""
        validator = VariableUsageValidator()

        click = ClickAction(
            target=Target(image="{{icon_path}}/button.png")
        )
        playbook = create_playbook(actions=[click])

        validator.validate(playbook)

        assert "icon_path" in validator.variable_references

    def test_extract_from_description(self):
        """Should extract variables from action description."""
        validator = VariableUsageValidator()

        click = ClickAction(
            target=Target(text="Button"),
            description="Click on {{action_name}}"
        )
        playbook = create_playbook(actions=[click])

        validator.validate(playbook)

        assert "action_name" in validator.variable_references
        refs = validator.variable_references["action_name"]
        assert refs[0][2] == "description"

    def test_extract_from_keyboard_action_text(self):
        """Should extract variables from KeyboardAction text field."""
        validator = VariableUsageValidator()

        keyboard = KeyboardAction(text="Hello {{username}}")
        playbook = create_playbook(actions=[keyboard])

        validator.validate(playbook)

        assert "username" in validator.variable_references
        refs = validator.variable_references["username"]
        assert refs[0][2] == "text"

    def test_extract_from_command_action_command(self):
        """Should extract variables from CommandAction command field."""
        validator = VariableUsageValidator()

        cmd = CommandAction(command="echo {{message}}")
        playbook = create_playbook(actions=[cmd])

        validator.validate(playbook)

        assert "message" in validator.variable_references
        refs = validator.variable_references["message"]
        assert refs[0][2] == "command"

    def test_extract_from_command_action_cwd(self):
        """Should extract variables from CommandAction cwd field."""
        validator = VariableUsageValidator()

        cmd = CommandAction(command="ls", cwd="{{working_dir}}")
        playbook = create_playbook(actions=[cmd])

        validator.validate(playbook)

        assert "working_dir" in validator.variable_references
        refs = validator.variable_references["working_dir"]
        assert refs[0][2] == "cwd"

    def test_extract_from_command_action_env(self):
        """Should extract variables from CommandAction env dict."""
        validator = VariableUsageValidator()

        cmd = CommandAction(
            command="echo $MY_VAR",
            env={"MY_VAR": "{{env_value}}"}
        )
        playbook = create_playbook(actions=[cmd])

        validator.validate(playbook)

        assert "env_value" in validator.variable_references
        refs = validator.variable_references["env_value"]
        assert refs[0][2] == "env.MY_VAR"

    def test_extract_from_drag_action(self):
        """Should extract variables from DragAction src and dst."""
        validator = VariableUsageValidator()

        drag = DragAction(
            src=Target(text="{{source_label}}"),
            dst=Target(text="{{dest_label}}")
        )
        playbook = create_playbook(actions=[drag])

        validator.validate(playbook)

        assert "source_label" in validator.variable_references
        assert "dest_label" in validator.variable_references

        src_refs = validator.variable_references["source_label"]
        assert src_refs[0][2] == "src.text"

        dst_refs = validator.variable_references["dest_label"]
        assert dst_refs[0][2] == "dst.text"

    def test_extract_from_pull_action_string_src(self):
        """Should extract variables from PullAction string src."""
        validator = VariableUsageValidator()

        pull = PullAction(src="{{source_path}}/file.txt")
        playbook = create_playbook(actions=[pull])

        validator.validate(playbook)

        assert "source_path" in validator.variable_references

    def test_extract_from_pull_action_list_src(self):
        """Should extract variables from PullAction list src."""
        validator = VariableUsageValidator()

        pull = PullAction(src=[
            "{{path1}}/file1.txt",
            "{{path2}}/file2.txt"
        ])
        playbook = create_playbook(actions=[pull])

        validator.validate(playbook)

        assert "path1" in validator.variable_references
        assert "path2" in validator.variable_references

    def test_extract_from_pull_action_dst(self):
        """Should extract variables from PullAction dst."""
        validator = VariableUsageValidator()

        pull = PullAction(src="/tmp/file.txt", dst="{{dest_folder}}")
        playbook = create_playbook(actions=[pull])

        validator.validate(playbook)

        assert "dest_folder" in validator.variable_references

    def test_extract_from_action_test_action_name(self):
        """Should extract variables from ActionTestAction name."""
        validator = VariableUsageValidator()

        test = ActionTestAction(name="{{test_name}}")
        playbook = create_playbook(actions=[test])

        validator.validate(playbook)

        assert "test_name" in validator.variable_references

    def test_extract_from_goto_action(self):
        """Should extract variables from GotoAction target."""
        validator = VariableUsageValidator()

        goto = GotoAction(target=Target(text="{{target_text}}"))
        playbook = create_playbook(actions=[goto])

        validator.validate(playbook)

        assert "target_text" in validator.variable_references

    def test_extract_from_block_action_nested(self):
        """Should extract variables from nested BlockAction."""
        validator = VariableUsageValidator()

        block = BlockAction(
            actions=[
                ClickAction(target=Target(text="{{nested_var}}")),
                KeyboardAction(text="{{another_var}}")
            ]
        )
        playbook = create_playbook(actions=[block])

        validator.validate(playbook)

        assert "nested_var" in validator.variable_references
        assert "another_var" in validator.variable_references

    def test_extract_from_deeply_nested_blocks(self):
        """Should extract variables from deeply nested BlockActions."""
        validator = VariableUsageValidator()

        inner_block = BlockAction(
            actions=[ClickAction(target=Target(text="{{deep_var}}"))]
        )
        outer_block = BlockAction(actions=[inner_block])
        playbook = create_playbook(actions=[outer_block])

        validator.validate(playbook)

        assert "deep_var" in validator.variable_references

    def test_extract_from_wait_until_exists_condition(self):
        """Should extract variables from WaitUntilAction exists condition."""
        validator = VariableUsageValidator()

        wait = WaitUntilAction(
            condition=WaitCondition(
                exists=Target(text="{{wait_text}}")
            )
        )
        playbook = create_playbook(actions=[wait])

        validator.validate(playbook)

        assert "wait_text" in validator.variable_references

    def test_extract_from_wait_until_not_exists_condition(self):
        """Should extract variables from WaitUntilAction not_exists condition."""
        validator = VariableUsageValidator()

        wait = WaitUntilAction(
            condition=WaitCondition(
                not_exists=Target(image="{{loading_image}}")
            )
        )
        playbook = create_playbook(actions=[wait])

        validator.validate(playbook)

        assert "loading_image" in validator.variable_references

    def test_extract_from_wait_until_all_condition(self):
        """Should extract variables from WaitUntilAction all (AND) condition."""
        validator = VariableUsageValidator()

        wait = WaitUntilAction(
            condition=WaitCondition(
                all=[
                    WaitCondition(exists=Target(text="{{cond1}}")),
                    WaitCondition(exists=Target(text="{{cond2}}"))
                ]
            )
        )
        playbook = create_playbook(actions=[wait])

        validator.validate(playbook)

        assert "cond1" in validator.variable_references
        assert "cond2" in validator.variable_references

    def test_extract_from_wait_until_any_condition(self):
        """Should extract variables from WaitUntilAction any (OR) condition."""
        validator = VariableUsageValidator()

        wait = WaitUntilAction(
            condition=WaitCondition(
                any=[
                    WaitCondition(exists=Target(text="{{opt1}}")),
                    WaitCondition(exists=Target(text="{{opt2}}"))
                ]
            )
        )
        playbook = create_playbook(actions=[wait])

        validator.validate(playbook)

        assert "opt1" in validator.variable_references
        assert "opt2" in validator.variable_references

    def test_extract_from_wait_until_negate_condition(self):
        """Should extract variables from WaitUntilAction negate (NOT) condition."""
        validator = VariableUsageValidator()

        wait = WaitUntilAction(
            condition=WaitCondition(
                negate=WaitCondition(exists=Target(text="{{not_var}}"))
            )
        )
        playbook = create_playbook(actions=[wait])

        validator.validate(playbook)

        assert "not_var" in validator.variable_references

    def test_extract_from_stop_action_condition(self):
        """Should extract variable from StopAction condition."""
        validator = VariableUsageValidator()

        stop = StopAction(
            condition=VariableCondition(variable="stop_var", equals=True)
        )
        playbook = create_playbook(actions=[stop])

        validator.validate(playbook)

        assert "stop_var" in validator.variable_references
        refs = validator.variable_references["stop_var"]
        assert refs[0][2] == "condition.variable"

    def test_extract_from_continue_action_condition(self):
        """Should extract variable from ContinueAction condition."""
        validator = VariableUsageValidator()

        cont = ContinueAction(
            condition=VariableCondition(variable="continue_var", equals="skip")
        )
        playbook = create_playbook(actions=[cont])

        validator.validate(playbook)

        assert "continue_var" in validator.variable_references

    def test_no_extraction_when_no_variables(self):
        """Should not extract anything when no variables are used."""
        validator = VariableUsageValidator()

        click = ClickAction(target=Target(text="Plain text"))
        playbook = create_playbook(actions=[click])

        validator.validate(playbook)

        assert len(validator.variable_references) == 0

    def test_multiple_references_same_variable(self):
        """Should track multiple references to the same variable."""
        validator = VariableUsageValidator()

        actions = [
            ClickAction(target=Target(text="{{shared_var}}")),
            KeyboardAction(text="{{shared_var}}"),
            CommandAction(command="echo {{shared_var}}")
        ]
        playbook = create_playbook(actions=actions)

        validator.validate(playbook)

        assert "shared_var" in validator.variable_references
        refs = validator.variable_references["shared_var"]
        assert len(refs) == 3


# === FilterValidator Tests ===

class TestFilterValidator:
    """Tests for FilterValidator."""

    def test_filter_pattern_simple(self):
        """FILTER_PATTERN should match simple filter syntax."""
        pattern = FilterValidator.FILTER_PATTERN

        matches = pattern.findall("| format")
        assert matches == ["format"]

    def test_filter_pattern_with_args(self):
        """FILTER_PATTERN should match filter with arguments."""
        pattern = FilterValidator.FILTER_PATTERN

        matches = pattern.findall("| format('%Y-%m-%d')")
        assert matches == ["format"]

    def test_filter_pattern_multiple_filters(self):
        """FILTER_PATTERN should match multiple filters in chain."""
        pattern = FilterValidator.FILTER_PATTERN

        matches = pattern.findall("| filter1 | filter2 | filter3")
        assert matches == ["filter1", "filter2", "filter3"]

    def test_filter_pattern_with_spaces(self):
        """FILTER_PATTERN should handle various spacing."""
        pattern = FilterValidator.FILTER_PATTERN

        matches = pattern.findall("|format")
        assert matches == ["format"]

        matches = pattern.findall("|  format")
        assert matches == ["format"]

    def test_type_filters_mapping(self):
        """TYPE_FILTERS should have expected filter mappings."""
        type_filters = FilterValidator.TYPE_FILTERS

        assert "TIMESTAMP" in type_filters
        assert "timezone" in type_filters["TIMESTAMP"]
        assert "format" in type_filters["TIMESTAMP"]
        assert "tolerance" in type_filters["TIMESTAMP"]
        assert "localtime" in type_filters["TIMESTAMP"]

        assert "STRING" in type_filters
        assert len(type_filters["STRING"]) == 0

    def test_validate_valid_timestamp_filter(self):
        """Should not error when valid filter is used on TIMESTAMP variable."""
        usage_validator = VariableUsageValidator()
        filter_validator = FilterValidator(usage_validator)

        # Create playbook with timestamp variable using format filter
        playbook = create_playbook(
            variables={"my_timestamp": "TIMESTAMP"},
            actions=[
                KeyboardAction(text="{{my_timestamp | format('%Y-%m-%d')}}")
            ]
        )

        # First run usage validator
        usage_validator.validate(playbook)

        # Then run filter validator
        result = filter_validator.validate(playbook)

        assert result.is_valid is True

    def test_validate_invalid_filter_on_string(self):
        """Should error when TIMESTAMP filter is used on STRING variable."""
        usage_validator = VariableUsageValidator()
        filter_validator = FilterValidator(usage_validator)

        playbook = create_playbook(
            variables={"my_string": "STRING"},
            actions=[
                KeyboardAction(text="{{my_string | format('%Y-%m-%d')}}")
            ]
        )

        usage_validator.validate(playbook)
        result = filter_validator.validate(playbook)

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "format" in result.errors[0].message
        assert "STRING" in result.errors[0].message

    def test_validate_unknown_filter(self):
        """Should error when unknown filter is used."""
        usage_validator = VariableUsageValidator()
        filter_validator = FilterValidator(usage_validator)

        playbook = create_playbook(
            variables={"my_var": "STRING"},
            actions=[
                KeyboardAction(text="{{my_var | unknown_filter}}")
            ]
        )

        usage_validator.validate(playbook)
        result = filter_validator.validate(playbook)

        assert result.is_valid is False
        assert "Unknown filter" in result.errors[0].message
        assert "unknown_filter" in result.errors[0].message

    def test_validate_skips_undefined_variables(self):
        """Should skip filter validation for undefined variables."""
        usage_validator = VariableUsageValidator()
        filter_validator = FilterValidator(usage_validator)

        # No variables defined, but used
        playbook = create_playbook(
            actions=[
                KeyboardAction(text="{{undefined_var | format}}")
            ]
        )

        usage_validator.validate(playbook)
        result = filter_validator.validate(playbook)

        # Filter validator should not error - VariableDefinitionValidator catches this
        assert result.is_valid is True

    def test_get_variable_types_from_save_timestamp(self):
        """Should detect TIMESTAMP type from SaveTimestampAction."""
        usage_validator = VariableUsageValidator()
        filter_validator = FilterValidator(usage_validator)

        playbook = create_playbook(
            actions=[
                SaveTimestampAction(variable="created_timestamp"),
                KeyboardAction(text="{{created_timestamp | format('%Y')}}")
            ]
        )

        usage_validator.validate(playbook)

        # Check that the filter validator correctly identifies the type
        types = filter_validator._get_variable_types(playbook)
        assert types["created_timestamp"] == "TIMESTAMP"

    def test_get_variable_types_from_command_capture(self):
        """Should detect STRING type from CommandAction capture."""
        usage_validator = VariableUsageValidator()
        filter_validator = FilterValidator(usage_validator)

        playbook = create_playbook(
            actions=[
                CommandAction(
                    command="hostname",
                    capture=CaptureSpec(variable="hostname_output")
                )
            ]
        )

        types = filter_validator._get_variable_types(playbook)
        assert types["hostname_output"] == "STRING"

    def test_get_variable_types_includes_automatic_vars(self):
        """Should include automatic variable types."""
        usage_validator = VariableUsageValidator()
        filter_validator = FilterValidator(usage_validator)

        playbook = create_playbook(actions=[])

        types = filter_validator._get_variable_types(playbook)

        assert types["adare_user_home"] == "PATH"
        assert types["adare_username"] == "STRING"
        assert types["adare_os"] == "STRING"

    def test_get_types_from_nested_block(self):
        """Should detect types from nested block actions."""
        usage_validator = VariableUsageValidator()
        filter_validator = FilterValidator(usage_validator)

        playbook = create_playbook(
            actions=[
                BlockAction(
                    actions=[
                        SaveTimestampAction(variable="block_timestamp"),
                        CommandAction(
                            command="date",
                            capture=CaptureSpec(variable="block_output")
                        )
                    ]
                )
            ]
        )

        types = filter_validator._get_variable_types(playbook)
        assert types["block_timestamp"] == "TIMESTAMP"
        assert types["block_output"] == "STRING"


# === DuplicateVariableValidator Tests ===

class TestDuplicateVariableValidator:
    """Tests for DuplicateVariableValidator."""

    def test_no_duplicates_no_warning(self):
        """Should not warn when variables are unique."""
        validator = DuplicateVariableValidator()

        playbook = create_playbook(
            variables={"var1": "STRING", "var2": "STRING"},
            actions=[SaveTimestampAction(variable="var3")]
        )

        result = validator.validate(playbook)

        assert len(result.warnings) == 0

    def test_duplicate_save_timestamp_warning(self):
        """Should warn when save_timestamp uses same variable twice."""
        validator = DuplicateVariableValidator()

        playbook = create_playbook(
            actions=[
                SaveTimestampAction(variable="my_timestamp"),
                SaveTimestampAction(variable="my_timestamp")
            ]
        )

        result = validator.validate(playbook)

        assert len(result.warnings) == 1
        assert "my_timestamp" in result.warnings[0]
        assert "defined multiple times" in result.warnings[0]

    def test_duplicate_variable_section_and_save_timestamp(self):
        """Should warn when variable defined in section and save_timestamp."""
        validator = DuplicateVariableValidator()

        playbook = create_playbook(
            variables={"shared_var": "STRING"},
            actions=[SaveTimestampAction(variable="shared_var")]
        )

        result = validator.validate(playbook)

        assert len(result.warnings) == 1
        assert "shared_var" in result.warnings[0]
        assert "variables section" in result.warnings[0]

    def test_duplicate_command_capture(self):
        """Should warn when command capture uses same variable twice."""
        validator = DuplicateVariableValidator()

        playbook = create_playbook(
            actions=[
                CommandAction(
                    command="cmd1",
                    capture=CaptureSpec(variable="output")
                ),
                CommandAction(
                    command="cmd2",
                    capture=CaptureSpec(variable="output")
                )
            ]
        )

        result = validator.validate(playbook)

        assert len(result.warnings) == 1
        assert "output" in result.warnings[0]

    def test_automatic_variable_override_warning(self):
        """Should warn when overriding automatic variable."""
        validator = DuplicateVariableValidator()

        playbook = create_playbook(
            variables={"adare_user_home": "STRING"}
        )

        result = validator.validate(playbook)

        # The DuplicateVariableValidator checks for duplicates within the playbook
        # It doesn't check against built-in automatic variables in the same way
        # Based on the code, it only warns if the variable appears multiple times
        # Let's check if there's a separate check for automatic variables
        # Looking at the code, it checks _is_automatic_variable when there are duplicates
        # So we need multiple definitions to trigger this

        # Actually, looking at the code more carefully, the duplicate check
        # only fires when len(sources) > 1, so a single definition won't trigger it
        # Let's test with a duplicate that overrides an automatic variable

        playbook = create_playbook(
            variables={"adare_user_home": "STRING"},
            actions=[SaveTimestampAction(variable="adare_user_home")]
        )

        result = validator.validate(playbook)

        assert len(result.warnings) == 1
        assert "automatic variable" in result.warnings[0].lower()

    def test_nested_block_duplicate_detection(self):
        """Should detect duplicates in nested blocks."""
        validator = DuplicateVariableValidator()

        playbook = create_playbook(
            actions=[
                SaveTimestampAction(variable="my_var"),
                BlockAction(
                    actions=[
                        SaveTimestampAction(variable="my_var")
                    ]
                )
            ]
        )

        result = validator.validate(playbook)

        assert len(result.warnings) == 1
        assert "my_var" in result.warnings[0]

    def test_template_variable_not_tracked(self):
        """Should not track variables with template syntax in name."""
        validator = DuplicateVariableValidator()

        playbook = create_playbook(
            actions=[
                SaveTimestampAction(variable="{{prefix}}_timestamp"),
                SaveTimestampAction(variable="{{prefix}}_timestamp")
            ]
        )

        result = validator.validate(playbook)

        # Template variables can't be statically determined, so no warning
        assert len(result.warnings) == 0

    def test_is_automatic_variable(self):
        """_is_automatic_variable should correctly identify automatic vars."""
        validator = DuplicateVariableValidator()

        assert validator._is_automatic_variable("adare_user_home") is True
        assert validator._is_automatic_variable("adare_username") is True
        assert validator._is_automatic_variable("adare_os") is True
        assert validator._is_automatic_variable("my_custom_var") is False
        assert validator._is_automatic_variable("adare_custom") is False


# === VariableDefinitionValidator Tests ===

class TestVariableDefinitionValidator:
    """Tests for VariableDefinitionValidator."""

    def test_defined_variable_no_error(self):
        """Should not error when used variable is defined."""
        usage_validator = VariableUsageValidator()
        def_validator = VariableDefinitionValidator(usage_validator)

        playbook = create_playbook(
            variables={"my_var": "STRING"},
            actions=[
                KeyboardAction(text="{{my_var}}")
            ]
        )

        usage_validator.validate(playbook)
        result = def_validator.validate(playbook)

        assert result.is_valid is True

    def test_undefined_variable_error(self):
        """Should error when variable is used but not defined."""
        usage_validator = VariableUsageValidator()
        def_validator = VariableDefinitionValidator(usage_validator)

        playbook = create_playbook(
            actions=[
                KeyboardAction(text="{{undefined_var}}")
            ]
        )

        usage_validator.validate(playbook)
        result = def_validator.validate(playbook)

        assert result.is_valid is False
        assert len(result.errors) == 1
        assert "undefined_var" in result.errors[0].message
        assert "not defined" in result.errors[0].message

    def test_automatic_variable_allowed(self):
        """Should not error when using automatic variables."""
        usage_validator = VariableUsageValidator()
        def_validator = VariableDefinitionValidator(usage_validator)

        playbook = create_playbook(
            actions=[
                KeyboardAction(text="Home: {{adare_user_home}}")
            ]
        )

        usage_validator.validate(playbook)
        result = def_validator.validate(playbook)

        assert result.is_valid is True

    def test_all_automatic_variables_recognized(self):
        """All automatic variables should be recognized as defined."""
        usage_validator = VariableUsageValidator()
        def_validator = VariableDefinitionValidator(usage_validator)

        automatic_vars = def_validator._get_automatic_variable_names()

        expected_vars = {
            'adare_user_home',
            'adare_username',
            'adare_user_documents',
            'adare_user_desktop',
            'adare_user_downloads',
            'adare_os',
            'adare_temp_dir',
            'adare_system_drive',
            'adare_root_dir',
            'adare_shared',
            'adare_shared_tools',
            'adare_shared_data',
            'adare_run_dir',
        }

        assert automatic_vars == expected_vars

    def test_save_timestamp_defines_variable(self):
        """Variable defined by SaveTimestampAction should be recognized."""
        usage_validator = VariableUsageValidator()
        def_validator = VariableDefinitionValidator(usage_validator)

        playbook = create_playbook(
            actions=[
                SaveTimestampAction(variable="my_timestamp"),
                KeyboardAction(text="{{my_timestamp}}")
            ]
        )

        usage_validator.validate(playbook)
        result = def_validator.validate(playbook)

        assert result.is_valid is True

    def test_command_capture_defines_variable(self):
        """Variable defined by CommandAction capture should be recognized."""
        usage_validator = VariableUsageValidator()
        def_validator = VariableDefinitionValidator(usage_validator)

        playbook = create_playbook(
            actions=[
                CommandAction(
                    command="hostname",
                    capture=CaptureSpec(variable="hostname")
                ),
                KeyboardAction(text="{{hostname}}")
            ]
        )

        usage_validator.validate(playbook)
        result = def_validator.validate(playbook)

        assert result.is_valid is True

    def test_nested_block_defines_variable(self):
        """Variable defined in nested block should be recognized."""
        usage_validator = VariableUsageValidator()
        def_validator = VariableDefinitionValidator(usage_validator)

        playbook = create_playbook(
            actions=[
                BlockAction(
                    actions=[
                        SaveTimestampAction(variable="block_ts")
                    ]
                ),
                KeyboardAction(text="{{block_ts}}")
            ]
        )

        usage_validator.validate(playbook)
        result = def_validator.validate(playbook)

        assert result.is_valid is True

    def test_multiple_undefined_variables(self):
        """Should report all undefined variables."""
        usage_validator = VariableUsageValidator()
        def_validator = VariableDefinitionValidator(usage_validator)

        playbook = create_playbook(
            actions=[
                KeyboardAction(text="{{var1}} and {{var2}}"),
                CommandAction(command="echo {{var3}}")
            ]
        )

        usage_validator.validate(playbook)
        result = def_validator.validate(playbook)

        assert result.is_valid is False
        # Each undefined variable should generate errors for each usage
        undefined_vars = {e.variable_name for e in result.errors}
        assert "var1" in undefined_vars
        assert "var2" in undefined_vars
        assert "var3" in undefined_vars

    def test_template_variable_name_ignored(self):
        """Variables with template syntax in save_timestamp should be ignored."""
        usage_validator = VariableUsageValidator()
        def_validator = VariableDefinitionValidator(usage_validator)

        playbook = create_playbook(
            actions=[
                # Template variable name can't be statically determined
                SaveTimestampAction(variable="{{prefix}}_timestamp")
            ]
        )

        defined = def_validator._collect_defined_variables(playbook)

        # Should not include template-based variable names
        assert "{{prefix}}_timestamp" not in defined


# === validate_playbook() Orchestration Tests ===

class TestValidatePlaybook:
    """Tests for validate_playbook() orchestration function."""

    def test_valid_playbook_no_error(self):
        """Should not raise for valid playbook."""
        playbook = create_playbook(
            variables={"my_var": "STRING"},
            actions=[
                KeyboardAction(text="{{my_var}}")
            ]
        )

        # Should not raise
        validate_playbook(playbook)

    def test_invalid_playbook_raises_value_error(self):
        """Should raise ValueError for invalid playbook."""
        playbook = create_playbook(
            actions=[
                KeyboardAction(text="{{undefined_var}}")
            ]
        )

        with pytest.raises(ValueError) as exc_info:
            validate_playbook(playbook)

        assert "validation failed" in str(exc_info.value).lower()
        assert "undefined_var" in str(exc_info.value)

    def test_error_message_contains_all_errors(self):
        """Error message should contain all validation errors."""
        playbook = create_playbook(
            actions=[
                KeyboardAction(text="{{var1}}"),
                CommandAction(command="{{var2}}")
            ]
        )

        with pytest.raises(ValueError) as exc_info:
            validate_playbook(playbook)

        error_msg = str(exc_info.value)
        assert "var1" in error_msg
        assert "var2" in error_msg

    def test_runs_all_validators(self):
        """validate_playbook should run all validators."""
        # Create playbook that exercises multiple validators
        playbook = create_playbook(
            variables={"defined_var": "STRING"},
            actions=[
                # For usage validator
                KeyboardAction(text="{{defined_var}}"),
                # For duplicate validator (will generate warning)
                SaveTimestampAction(variable="ts1"),
                SaveTimestampAction(variable="ts1"),  # Duplicate
            ]
        )

        # Should complete without error (duplicates are warnings, not errors)
        validate_playbook(playbook)

    def test_empty_playbook_valid(self):
        """Empty playbook should be valid."""
        playbook = create_playbook(actions=[])

        # Should not raise
        validate_playbook(playbook)

    def test_only_automatic_variables_valid(self):
        """Playbook using only automatic variables should be valid."""
        playbook = create_playbook(
            actions=[
                CommandAction(command="echo {{adare_user_home}}"),
                KeyboardAction(text="User: {{adare_username}}")
            ]
        )

        # Should not raise
        validate_playbook(playbook)

    def test_complex_valid_playbook(self):
        """Complex but valid playbook should pass validation."""
        playbook = create_playbook(
            variables={
                "app_name": "STRING",
                "config_path": "PATH"
            },
            actions=[
                # Using defined variables
                ClickAction(target=Target(text="{{app_name}}")),

                # Using automatic variables
                CommandAction(command="cd {{adare_user_home}}"),

                # Nested block with variables
                BlockAction(
                    actions=[
                        SaveTimestampAction(variable="start_time"),
                        KeyboardAction(text="Started at {{start_time}}")
                    ]
                ),

                # WaitUntil with variables
                WaitUntilAction(
                    condition=WaitCondition(
                        exists=Target(text="{{app_name}}")
                    )
                )
            ]
        )

        # Should not raise
        validate_playbook(playbook)


# === Edge Cases and Regression Tests ===

class TestEdgeCases:
    """Edge cases and regression tests."""

    def test_empty_string_no_variables(self):
        """Empty strings should not cause issues."""
        validator = VariableUsageValidator()

        playbook = create_playbook(
            actions=[
                KeyboardAction(text=""),
                CommandAction(command="echo hello")
            ]
        )

        result = validator.validate(playbook)
        assert result.is_valid is True
        assert len(validator.variable_references) == 0

    def test_special_characters_in_text(self):
        """Special characters without variables should not match."""
        validator = VariableUsageValidator()

        playbook = create_playbook(
            actions=[
                KeyboardAction(text="Text with {curly} and {{incomplete")
            ]
        )

        result = validator.validate(playbook)
        assert len(validator.variable_references) == 0

    def test_nested_curly_braces(self):
        """Nested curly braces should be handled correctly."""
        pattern = VariableUsageValidator.VARIABLE_PATTERN

        # This is not a valid variable reference
        matches = pattern.findall("{{{var}}}")
        # Should still extract 'var' from the inner valid pattern
        assert matches == ["var"]

    def test_variable_with_underscore_and_numbers(self):
        """Variables with underscores and numbers should match."""
        validator = VariableUsageValidator()

        playbook = create_playbook(
            actions=[
                KeyboardAction(text="{{my_var_123}}")
            ]
        )

        validator.validate(playbook)
        assert "my_var_123" in validator.variable_references

    def test_none_values_in_actions(self):
        """None values in optional fields should not cause errors."""
        validator = VariableUsageValidator()

        # Action with all optional fields as None
        cmd = CommandAction(
            command="echo test",
            cwd=None,
            env=None
        )
        playbook = create_playbook(actions=[cmd])

        result = validator.validate(playbook)
        assert result.is_valid is True

    def test_action_without_description(self):
        """Actions without description should work."""
        validator = VariableUsageValidator()

        click = ClickAction(target=Target(text="Button"))
        playbook = create_playbook(actions=[click])

        result = validator.validate(playbook)
        assert result.is_valid is True

    def test_drag_action_with_none_targets(self):
        """DragAction should handle targets correctly."""
        validator = VariableUsageValidator()

        # Normal drag action
        drag = DragAction(
            src=Target(position=[100, 100]),
            dst=Target(position=[200, 200])
        )
        playbook = create_playbook(actions=[drag])

        result = validator.validate(playbook)
        assert result.is_valid is True

    def test_pull_action_empty_src_list(self):
        """PullAction with empty list should be handled."""
        validator = VariableUsageValidator()

        # This would likely be caught elsewhere, but validator should handle it
        pull = PullAction(src=[])
        playbook = create_playbook(actions=[pull])

        result = validator.validate(playbook)
        assert result.is_valid is True

    def test_stop_action_without_condition(self):
        """StopAction without condition should be handled."""
        validator = VariableUsageValidator()

        stop = StopAction()  # No condition
        playbook = create_playbook(actions=[stop])

        result = validator.validate(playbook)
        assert result.is_valid is True
        assert len(validator.variable_references) == 0

    def test_continue_action_without_condition(self):
        """ContinueAction without condition should be handled."""
        validator = VariableUsageValidator()

        cont = ContinueAction()  # No condition
        playbook = create_playbook(actions=[cont])

        result = validator.validate(playbook)
        assert result.is_valid is True

    def test_filter_extraction_from_nested_field(self):
        """Filter extraction should handle nested field names."""
        usage_validator = VariableUsageValidator()
        filter_validator = FilterValidator(usage_validator)

        playbook = create_playbook(
            variables={"my_ts": "TIMESTAMP"},
            actions=[
                ClickAction(
                    target=Target(text="{{my_ts | format('%H:%M')}}")
                )
            ]
        )

        usage_validator.validate(playbook)
        result = filter_validator.validate(playbook)

        assert result.is_valid is True

    def test_multiple_same_variable_same_action(self):
        """Same variable used multiple times in same action field."""
        validator = VariableUsageValidator()

        playbook = create_playbook(
            actions=[
                KeyboardAction(text="{{var}} and {{var}} again")
            ]
        )

        validator.validate(playbook)

        assert "var" in validator.variable_references
        refs = validator.variable_references["var"]
        # Should have 2 references
        assert len(refs) == 2


# === Parametrized Pattern Tests ===

class TestPatternMatching:
    """Parametrized tests for regex patterns."""

    @pytest.mark.parametrize("text,should_match", [
        ("{{var}}", True),
        ("{{ var }}", True),
        ("{{var|filter}}", True),
        ("{{var | filter}}", True),
        ("{{var | filter1 | filter2}}", True),
        ("{var}", False),  # Single braces
        ("{ {var} }", False),  # Separated braces
        ("{{123var}}", True),  # Starts with number - \w+ matches digits
        ("{{var-name}}", False),  # Dash not allowed
        ("{{var.name}}", False),  # Dot not allowed
        ("{{  }}", False),  # Empty
    ])
    def test_variable_pattern_matching(self, text, should_match):
        """Test variable pattern with various inputs."""
        pattern = VariableUsageValidator.VARIABLE_PATTERN
        matches = pattern.findall(text)

        if should_match:
            assert len(matches) > 0
        else:
            assert len(matches) == 0

    @pytest.mark.parametrize("text,expected_filters", [
        ("| format", ["format"]),
        ("|format", ["format"]),
        ("| filter1 | filter2", ["filter1", "filter2"]),
        ("| format('%Y')", ["format"]),
        ("| filter1('arg') | filter2", ["filter1", "filter2"]),
        ("|  spaced  |another", ["spaced", "another"]),
    ])
    def test_filter_pattern_matching(self, text, expected_filters):
        """Test filter pattern extraction."""
        pattern = FilterValidator.FILTER_PATTERN
        matches = pattern.findall(text)
        assert matches == expected_filters


# === Integration Tests ===

class TestIntegration:
    """Integration tests combining multiple validators."""

    def test_full_validation_workflow(self):
        """Test complete validation workflow with various actions."""
        playbook = create_playbook(
            variables={
                "user_name": "STRING",
                "config_dir": "PATH"
            },
            actions=[
                # Valid variable usage
                KeyboardAction(text="Hello {{user_name}}"),

                # Command with defined variable
                CommandAction(command="ls {{config_dir}}"),

                # Automatic variable
                CommandAction(command="cd {{adare_user_home}}"),

                # Save timestamp creates new variable
                SaveTimestampAction(variable="action_time"),

                # Use the created variable
                KeyboardAction(text="Done at {{action_time}}"),

                # Nested block
                BlockAction(
                    actions=[
                        CommandAction(
                            command="whoami",
                            capture=CaptureSpec(variable="current_user")
                        ),
                        KeyboardAction(text="User: {{current_user}}")
                    ]
                )
            ]
        )

        # Should pass all validation
        validate_playbook(playbook)

    def test_validation_failure_with_multiple_issues(self):
        """Test that all validation issues are collected."""
        playbook = create_playbook(
            variables={"defined": "STRING"},
            actions=[
                # Undefined variable
                KeyboardAction(text="{{undefined}}"),

                # Another undefined variable
                CommandAction(command="{{also_undefined}}"),
            ]
        )

        with pytest.raises(ValueError) as exc_info:
            validate_playbook(playbook)

        error_msg = str(exc_info.value)
        assert "undefined" in error_msg
        assert "also_undefined" in error_msg

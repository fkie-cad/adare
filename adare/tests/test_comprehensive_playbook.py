#!/usr/bin/env python3

import pytest
from pathlib import Path
from adare.types.playbook import parse_playbook

class TestComprehensivePlaybook:
    """Comprehensive tests for all playbook functionality combinations."""
    
    @pytest.fixture
    def config(self):
        """Load the comprehensive test playbook."""
        test_file = Path(__file__).parent / "files" / "comprehensive_playbook.yaml"
        return parse_playbook(test_file)
    
    def test_settings_parsing(self, config):
        """Test all settings variations are parsed correctly."""
        assert config.settings.idle == 2.5
        assert config.settings.timeout == 600
        assert config.settings.screenshot is not None
        assert config.settings.screenshot["format"] == "jpg"
        assert config.settings.screenshot["quality"] == 80
    
    def test_variables_parsing(self, config):
        """Test variable definitions with templates."""
        assert config.variables is not None
        assert config.variables["username"] == "testuser"
        assert config.variables["password"] == "secret123"
        assert config.variables["filepath"] == "/home/{{ username }}/testfile.txt"
        assert config.variables["url"] == "https://example.com/{{ username }}"
        assert config.variables["timeout_value"] == 30
    
    
    def test_action_types_coverage(self, config):
        """Test that all action types are present and parsed."""
        action_types = [type(action).__name__ for action in config.actions]
        
        # Verify all action types are present
        expected_types = [
            "CommandAction", "ClickAction", "RightClickAction", "DoubleClickAction",
            "DragAction", "KeyboardAction", "IdleAction", "ScrollAction", 
            "GotoAction", "ScreenshotAction", "SaveTimestampAction", 
            "ActionTestAction", "BlockAction"
        ]
        
        for expected_type in expected_types:
            assert expected_type in action_types, f"Missing action type: {expected_type}"
    
    def test_command_actions_variations(self, config):
        """Test different CommandAction configurations."""
        command_actions = [a for a in config.actions if type(a).__name__ == "CommandAction"]
        assert len(command_actions) >= 3
        
        # Test basic command with cmd
        basic_cmd = command_actions[0]
        assert basic_cmd.name == "Setup Environment"
        assert basic_cmd.cmd == "mkdir -p /home/{{ username }}/testdir"
        assert basic_cmd.timeout == 10
        
        # Test command with tool
        tool_cmd = command_actions[1]
        assert tool_cmd.tool == "curl"
        assert tool_cmd.command == "curl -o {{ filepath }} {{ url }}"
        assert tool_cmd.cwd == "/tmp"
        assert tool_cmd.env["USER"] == "{{ username }}"
        assert tool_cmd.shell == True
        
        # Test complex command
        complex_cmd = command_actions[-1]  # Last command action
        assert complex_cmd.name == "Complex Command"
        assert "{{ username }}" in complex_cmd.cmd
        assert complex_cmd.timeout == 60.0
        assert complex_cmd.shell == True
    
    def test_click_actions_targets(self, config):
        """Test different click target types."""
        click_actions = [a for a in config.actions if type(a).__name__ == "ClickAction"]
        assert len(click_actions) >= 3
        
        # Image target
        image_click = click_actions[0]
        assert image_click.target.image == "button.png"
        assert image_click.target.text is None
        assert image_click.target.position is None
        
        # Text target
        text_click = click_actions[1]
        assert text_click.target.text == "Login"
        assert text_click.target.image is None
        
        # Position target
        pos_click = click_actions[2]
        assert pos_click.target.position == [100, 200]
        assert pos_click.target.text is None
        assert pos_click.target.image is None
    
    def test_keyboard_actions_variations(self, config):
        """Test different keyboard action types."""
        keyboard_actions = [a for a in config.actions if type(a).__name__ == "KeyboardAction"]
        assert len(keyboard_actions) >= 3
        
        # Keys typing
        keys_action = keyboard_actions[0]
        assert keys_action.keys == "{{ username }}"
        assert keys_action.combination is None
        
        # Combination/hotkey
        combo_action = keyboard_actions[1]
        assert combo_action.combination == ["ctrl", "c"]
        assert combo_action.keys is None
        
        # Conditional keyboard action
        conditional_action = keyboard_actions[2]
        assert conditional_action.keys == "test input"
        assert conditional_action.when is not None
        assert len(conditional_action.when) == 1
        assert conditional_action.when[0].text == "Input Field"
    
    def test_screenshot_actions_variations(self, config):
        """Test full and partial screenshot actions."""
        screenshot_actions = [a for a in config.actions if type(a).__name__ == "ScreenshotAction"]
        assert len(screenshot_actions) >= 2
        
        # Full screenshot
        full_screenshot = screenshot_actions[0]
        assert full_screenshot.x is None
        assert full_screenshot.y is None
        assert full_screenshot.width is None
        assert full_screenshot.height is None
        
        # Partial screenshot
        partial_screenshot = screenshot_actions[1]
        assert partial_screenshot.x == 100
        assert partial_screenshot.y == 200
        assert partial_screenshot.width == 400
        assert partial_screenshot.height == 300
    
    def test_test_actions_variations(self, config):
        """Test inline and detailed test actions."""
        test_actions = [a for a in config.actions if type(a).__name__ == "ActionTestAction"]
        assert len(test_actions) >= 3
        
        # Inline test
        inline_test = test_actions[0]
        assert inline_test.name == "file_exists"
        
        # Detailed test
        detailed_test = test_actions[1]
        assert detailed_test.name == "network_test"
        assert detailed_test.description == "Run network connectivity test"
    
    def test_block_actions_basic(self, config):
        """Test basic block actions without conditions."""
        block_actions = [a for a in config.actions if type(a).__name__ == "BlockAction"]
        assert len(block_actions) >= 6  # We have several block variations
        
        # Simple block
        simple_block = block_actions[0]
        assert simple_block.description == "Simple block of actions"
        assert simple_block.when is None
        assert len(simple_block.actions) == 3
        
        # Check nested action types
        nested_types = [type(a).__name__ for a in simple_block.actions]
        assert "CommandAction" in nested_types
        assert "IdleAction" in nested_types
    
    def test_block_conditions_exists(self, config):
        """Test block with exists conditions."""
        block_actions = [a for a in config.actions if type(a).__name__ == "BlockAction"]
        
        # Find block with exists condition
        exists_block = None
        for block in block_actions:
            if block.when and len(block.when) == 1 and hasattr(block.when[0], 'text'):
                if block.when[0].text == "Continue":
                    exists_block = block
                    break
        
        assert exists_block is not None
        assert exists_block.description == "Block with exists condition"
        assert len(exists_block.when) == 1
        assert exists_block.when[0].text == "Continue"
        assert len(exists_block.actions) == 2
    
    def test_block_conditions_not_exists(self, config):
        """Test block with not_exists conditions."""
        block_actions = [a for a in config.actions if type(a).__name__ == "BlockAction"]
        
        # Find block with not_exists condition
        not_exists_block = None
        for block in block_actions:
            if (block.when and len(block.when) == 1 and 
                hasattr(block.when[0], 'image') and 
                block.when[0].image == "error.png"):
                not_exists_block = block
                break
        
        assert not_exists_block is not None
        assert not_exists_block.description == "Block with not_exists condition"
        assert len(not_exists_block.when) == 1
        assert not_exists_block.when[0].image == "error.png"
    
    def test_block_multiple_conditions(self, config):
        """Test block with multiple conditions."""
        block_actions = [a for a in config.actions if type(a).__name__ == "BlockAction"]
        
        # Find block with multiple conditions
        multi_condition_block = None
        for block in block_actions:
            if block.when and len(block.when) == 2:
                multi_condition_block = block
                break
        
        assert multi_condition_block is not None
        assert multi_condition_block.description == "Block with multiple conditions"
        assert len(multi_condition_block.when) == 2
        
        # Check both conditions exist
        condition_types = [type(condition).__name__ for condition in multi_condition_block.when]
        assert "ExistsCondition" in condition_types
        assert "NotExistsCondition" in condition_types
    
    def test_nested_blocks(self, config):
        """Test nested block structures."""
        block_actions = [a for a in config.actions if type(a).__name__ == "BlockAction"]
        
        # Find the outer block that contains nested blocks
        outer_block = None
        for block in block_actions:
            if block.description == "Outer block":
                outer_block = block
                break
        
        assert outer_block is not None
        assert len(outer_block.actions) == 3  # start command, inner block, end command
        
        # Find the nested block
        inner_block = None
        for action in outer_block.actions:
            if type(action).__name__ == "BlockAction":
                inner_block = action
                break
        
        assert inner_block is not None
        assert inner_block.description == "Inner block"
        assert inner_block.when is not None
        assert len(inner_block.when) == 1
        assert inner_block.when[0].text == "Inner Condition"
    
    def test_drag_action_targets(self, config):
        """Test drag action with source and destination targets."""
        drag_actions = [a for a in config.actions if type(a).__name__ == "DragAction"]
        assert len(drag_actions) >= 1
        
        drag_action = drag_actions[0]
        assert drag_action.source.image == "file.png"
        assert drag_action.destination.text == "Trash"
        assert drag_action.description == "Drag file to trash"
    
    def test_save_timestamp_actions(self, config):
        """Test timestamp saving actions."""
        timestamp_actions = [a for a in config.actions if type(a).__name__ == "SaveTimestampAction"]
        assert len(timestamp_actions) >= 2
        
        start_timestamp = timestamp_actions[0]
        assert start_timestamp.variable == "TIMESTAMP.START"
        
        end_timestamp = timestamp_actions[1]
        assert end_timestamp.variable == "TIMESTAMP.END"
    
    def test_all_gui_actions_present(self, config):
        """Test that all GUI action types are present."""
        action_types = [type(action).__name__ for action in config.actions]
        
        gui_actions = [
            "ClickAction", "RightClickAction", "DoubleClickAction", 
            "DragAction", "ScrollAction", "GotoAction"
        ]
        
        for gui_action in gui_actions:
            assert gui_action in action_types
    
    def test_total_action_count(self, config):
        """Test that we have a reasonable number of actions covering all cases."""
        assert len(config.actions) >= 20  # Should have many actions to test everything
        
        # Count action types
        action_type_counts = {}
        for action in config.actions:
            action_type = type(action).__name__
            action_type_counts[action_type] = action_type_counts.get(action_type, 0) + 1
        
        # Verify we have multiple instances of key action types
        assert action_type_counts.get("CommandAction", 0) >= 3
        assert action_type_counts.get("ClickAction", 0) >= 3
        assert action_type_counts.get("BlockAction", 0) >= 5
        assert action_type_counts.get("KeyboardAction", 0) >= 3
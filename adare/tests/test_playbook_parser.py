#!/usr/bin/env python3

import pytest
from pathlib import Path
from adare.types.playbook import parse_playbook

class TestPlaybookParser:
    """Test the playbook parser with various YAML configurations."""
    
    def test_parse_example_playbook(self):
        """Test that the parser can handle the example YAML file."""
        test_file = Path(__file__).parent / "files" / "test_playbook.yaml"
        
        config = parse_playbook(test_file)
        
        # Test settings
        assert config.settings.idle == 1.0
        assert config.settings.timeout == 300
        assert config.settings.screenshot is not None
        assert config.settings.screenshot["format"] == "png"
        assert config.settings.screenshot["quality"] == 95
        
        # Test variables
        assert config.variables is not None
        assert config.variables["username"] == "vagrant"
        assert "filepath" in config.variables
        
        # Test actions
        assert len(config.actions) > 0
        
        # Check that we have the expected action types
        action_types = [type(action).__name__ for action in config.actions]
        assert "CommandAction" in action_types
        assert "ActionTestAction" in action_types
        assert "ClickAction" in action_types
        assert "IdleAction" in action_types
        assert "KeyboardAction" in action_types
        assert "SaveTimestampAction" in action_types
        assert "BlockAction" in action_types
    
    def test_command_action_parsing(self):
        """Test that CommandAction is parsed correctly."""
        test_file = Path(__file__).parent / "files" / "test_playbook.yaml"
        config = parse_playbook(test_file)
        
        # Find the first command action
        command_actions = [a for a in config.actions if type(a).__name__ == "CommandAction"]
        assert len(command_actions) > 0
        
        first_command = command_actions[0]
        assert first_command.name == "Create Test File"
        assert first_command.description == "create the to deleted file"
        assert first_command.cmd is not None
    
    def test_block_action_parsing(self):
        """Test that BlockAction with nested actions is parsed correctly."""
        test_file = Path(__file__).parent / "files" / "test_playbook.yaml"
        config = parse_playbook(test_file)
        
        # Find the block action
        block_actions = [a for a in config.actions if type(a).__name__ == "BlockAction"]
        assert len(block_actions) > 0
        
        block_action = block_actions[0]
        assert block_action.description == "Check if file metadata exists in trash bin"
        assert len(block_action.actions) > 0
        
        # Check nested actions
        nested_action_types = [type(action).__name__ for action in block_action.actions]
        assert "CommandAction" in nested_action_types
        assert "ActionTestAction" in nested_action_types
    
    def test_variables_are_parsed(self):
        """Test that variables are correctly parsed and stored."""
        test_file = Path(__file__).parent / "files" / "test_playbook.yaml"
        config = parse_playbook(test_file)
        
        # Verify variables are parsed
        assert config.variables is not None
        assert config.variables["username"] == "vagrant"
        assert config.variables["filepath"] == "C:/Users/{{ username }}/Documents/testfile.txt"
        
        # Note: The template {{ username }} is NOT resolved during parsing
        # Template resolution happens during execution, not parsing
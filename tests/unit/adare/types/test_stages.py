"""Unit tests for Stage classes and hidden stage behavior."""
import pytest
from adare.types.stages import (
    Stage,
    VMRuntimePreparationStage,
    VMInstanceSyncStage,
    VMStartStage,
    VirtualMachineSetupStage,
)


class TestStageHiddenAttribute:
    """Test hidden attribute behavior for stages."""

    def test_hidden_stage_runtime_preparation(self):
        """VMRuntimePreparationStage should be hidden."""
        stage = VMRuntimePreparationStage()
        assert stage.hidden is True
        assert stage.should_hide() is True

    def test_hidden_stage_instance_sync(self):
        """VMInstanceSyncStage should be hidden."""
        stage = VMInstanceSyncStage()
        assert stage.hidden is True
        assert stage.should_hide() is True

    def test_visible_stage_vm_start(self):
        """VMStartStage should be visible."""
        stage = VMStartStage()
        assert stage.hidden is False
        assert stage.should_hide() is False

    def test_visible_stage_vm_setup(self):
        """VirtualMachineSetupStage should be visible."""
        stage = VirtualMachineSetupStage()
        assert stage.hidden is False
        assert stage.should_hide() is False

    def test_stage_serialization_preserves_hidden(self):
        """Serialization should preserve hidden flag."""
        stage = VMRuntimePreparationStage()
        serialized = stage.to_dict()
        assert serialized['hidden'] is True
        assert serialized['name'] == 'vm_runtime_preparation'

    def test_stage_deserialization_preserves_hidden(self):
        """Deserialization should preserve hidden flag accessibility."""
        stage = VMRuntimePreparationStage()
        serialized = stage.to_dict()
        deserialized = Stage.from_dict(serialized)

        assert deserialized.hidden is True
        assert deserialized.should_hide() is True
        assert type(deserialized).__name__ == 'VMRuntimePreparationStage'

    def test_stage_deserialization_vm_instance_sync(self):
        """Deserialization should work for VMInstanceSyncStage."""
        stage = VMInstanceSyncStage()
        serialized = stage.to_dict()
        deserialized = Stage.from_dict(serialized)

        assert deserialized.hidden is True
        assert deserialized.should_hide() is True
        assert type(deserialized).__name__ == 'VMInstanceSyncStage'

    def test_should_hide_skipped_message(self):
        """Stages with SKIPPED in sub_msg should be hidden."""
        stage = VMStartStage()  # Normally visible
        assert stage.should_hide() is False

        stage.sub_msg = "SKIPPED: some reason"
        assert stage.should_hide() is True

    def test_should_hide_skipped_message_case_sensitive(self):
        """SKIPPED check should be case-sensitive."""
        stage = VMStartStage()

        stage.sub_msg = "skipped: lowercase"
        # Current implementation is case-sensitive (checks for "SKIPPED")
        assert stage.should_hide() is False

        stage.sub_msg = "SKIPPED: uppercase"
        assert stage.should_hide() is True

    def test_visible_stage_serialization(self):
        """Visible stages should have hidden=False in serialization."""
        stage = VMStartStage()
        serialized = stage.to_dict()
        assert serialized['hidden'] is False

    def test_round_trip_serialization_hidden_stage(self):
        """Full round-trip serialization should preserve all attributes."""
        original = VMRuntimePreparationStage()
        original.sub_msg = "Test message"

        # Serialize
        serialized = original.to_dict()

        # Deserialize
        restored = Stage.from_dict(serialized)

        # Verify all attributes match
        assert restored.name == original.name
        assert restored.hidden == original.hidden
        assert restored.msg == original.msg
        assert restored.sub_msg == original.sub_msg
        assert restored.should_hide() == original.should_hide()

    def test_round_trip_serialization_visible_stage(self):
        """Full round-trip serialization for visible stages."""
        original = VMStartStage()
        original.sub_msg = "Starting VM"

        # Serialize
        serialized = original.to_dict()

        # Deserialize
        restored = Stage.from_dict(serialized)

        # Verify all attributes match
        assert restored.name == original.name
        assert restored.hidden == original.hidden
        assert restored.msg == original.msg
        assert restored.sub_msg == original.sub_msg
        assert restored.should_hide() == original.should_hide()

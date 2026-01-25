
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
from datetime import datetime

from adare.backend.experiment.run import (
    step_initialize,
    step_setup_experiment_environment,
    step_validate_integrity,
    step_prepare_run_environment,
    ExperimentRunCtx,
    ExperimentConfig
)

@pytest.fixture
def run_ctx():
    config = ExperimentConfig(
        project_path=Path("/tmp/proj"),
        experiment_name="exp1",
        environment_name="env1"
    )
    return ExperimentRunCtx(config)

class TestExperimentRun:

    @patch('adare.backend.experiment.run.experiment_database')
    def test_step_initialize(self, mock_db, run_ctx):
        mock_db.initialize_experiment_run.return_value = "01HR..."
        
        step_initialize(run_ctx)
        
        assert run_ctx.experiment_run_ulid == "01HR..."
        assert isinstance(run_ctx.timestamp_start, datetime)
        mock_db.initialize_experiment_run.assert_called_once()

    @patch('adare.backend.experiment.run.ProjectDirectory')
    @patch('adare.backend.experiment.run.ExperimentDirectory')
    @patch('adare.backend.experiment.run.experiment_database')
    @patch('adare.backend.experiment.run.environment_database')
    @patch('adare.backend.experiment.run.StageCtxManager')
    def test_step_setup_experiment_env(
        self, mock_stage_mgr, mock_env_db, mock_exp_db, 
        mock_exp_dir_cls, mock_proj_dir_cls, run_ctx
    ):
        # Setup mocks
        mock_env_db.get_environment_ulid.return_value = "env_ulid"
        mock_env_db.get_environment_vm_file.return_value = Path("vm.qcow2")
        mock_env_db.get_environment_os.return_value = "linux"
        mock_env_db.get_environment_hypervisor.return_value = "qemu"
        mock_env_db.get_environment_path_by_project_and_name.return_value = Path("env.yaml")
        
        mock_exp_db.get_experiment_by_project_and_name.return_value = "exp_id"
        
        # Prevent actual DB load for playbook
        with patch('adare.database.api.playbook.PlaybookApi') as mock_pb_api:
             mock_pb_api.return_value.__enter__.return_value.load_playbook_from_database.return_value = MagicMock(actions=[])
             
             step_setup_experiment_environment(run_ctx)
             
        assert run_ctx.guest_platform == "linux"
        assert run_ctx.hypervisor_type == "qemu"
        mock_exp_db.set_experiment_run_base_info.assert_called_once()

    @patch('adare.backend.experiment.run.StageCtxManager')
    def test_step_validate_integrity_skip(self, mock_stage_mgr, run_ctx):
        run_ctx.test_mode = True
        
        step_validate_integrity(run_ctx)
        
        # Should not raise or call DB integrity checks
        # Verify stage status logic was called to update skip message
        mock_stage_mgr.return_value.__enter__.return_value.set_status.assert_called()

    @patch('adare.backend.experiment.run.ExperimentRunDirectory')
    @patch('adare.backend.experiment.run.StageCtxManager')
    @patch.multiple('pathlib.Path', unlink=MagicMock(return_value=None), exists=MagicMock(return_value=True))
    def test_step_prepare_run_env(self, mock_stage_mgr, mock_run_dir_cls, run_ctx):
        # We need to mock Path objects specifically for the poetry lock checks
        # But patching Path.exists globally is risky.
        # Instead, let's rely on the mocks behaving reasonably or mocking specific paths if needed.
        # Here we assume unlink won't fail.
        
        step_prepare_run_environment(run_ctx)
        
        mock_run_dir_cls.return_value.create.assert_called_once()
        assert run_ctx.experiment_run_directory is not None

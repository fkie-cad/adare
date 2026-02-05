"""
AdareAPI - Facade for ADARE services.

Provides a unified API interface for web and CLI frontends.

Available API facades:
- api.devmode - Development mode operations
- api.testfunction - Test function management
- api.experiment - Experiment lifecycle operations
- api.manage - Database and system management
- api.environment - Environment configuration
- api.project - Project management
- api.show - Data retrieval and display
- api.vm - Virtual machine operations
- api.web - Web integration and sync

All API methods return Result[T] objects for consistent error handling.
"""


class DevModeAPI:
    """Dev mode operations API."""

    def __init__(self):
        # Lazy import to avoid circular dependencies
        from adare.services import devmode_service
        self._service = devmode_service.DevModeService()

    def start_session(self, request):
        """Start a new dev mode session."""
        return self._service.start_session(request)

    def stop_session(self, request):
        """Stop a dev mode session."""
        return self._service.stop_session(request)

    def list_sessions(self, request):
        """List all dev mode sessions."""
        return self._service.list_sessions(request)

    def get_session_state(self, request):
        """Get session state."""
        return self._service.get_session_state(request)

    def cleanup_sessions(self, request):
        """Cleanup stale sessions."""
        return self._service.cleanup_sessions(request)

    def reset_session(self, request):
        """Reset session (soft or hard)."""
        return self._service.reset_session(request)

    def execute_action(self, request):
        """Execute a single action."""
        return self._service.execute_action(request)

    def execute_playbook(self, request):
        """Execute a playbook."""
        return self._service.execute_playbook(request)

    def create_checkpoint(self, request):
        """Create a checkpoint."""
        return self._service.create_checkpoint(request)

    def restore_checkpoint(self, request):
        """Restore a checkpoint."""
        return self._service.restore_checkpoint(request)

    def list_checkpoints(self, request):
        """List checkpoints."""
        return self._service.list_checkpoints(request)

    def delete_checkpoint(self, request):
        """Delete a checkpoint."""
        return self._service.delete_checkpoint(request)

    def update_testfunctions(self, request):
        """Update testfunctions."""
        return self._service.update_testfunctions(request)

    def restart_cv_server(self, request):
        """Restart CV server."""
        return self._service.restart_cv_server(request)

    def stop_cv_server(self, request):
        """Stop CV server."""
        return self._service.stop_cv_server(request)

    def execute_playbook_batch(self, request):
        """Execute batch of playbooks with checkpoint restoration."""
        return self._service.execute_playbook_batch(request)

    def resume_session(self, session_id, console_ulid=None):
        """Resume a specific dev mode session by ID."""
        return self._service.resume_session(session_id, console_ulid=console_ulid)

    def resume_most_recent(self, project_path, console_ulid=None):
        """Resume the most recently stopped dev mode session."""
        return self._service.resume_most_recent(project_path, console_ulid=console_ulid)


class TestFunctionAPI:
    """Testfunction operations API."""

    def __init__(self):
        # Lazy import to avoid circular dependencies
        from adare.services import testfunction_service
        self._service = testfunction_service.TestfunctionService()

    def create(self, request):
        """Create a new testfunction."""
        return self._service.create(request)

    def load(self, request):
        """Load a testfunction."""
        return self._service.load(request)

    def remove(self, name, force=False):
        """Remove a testfunction."""
        return self._service.remove(name, force=force)

    def list_all(self):
        """List all testfunctions."""
        return self._service.list_all()

    def exists(self, name):
        """Check if testfunction exists."""
        return self._service.exists(name)

    def get_usage(self, name):
        """Get testfunction usage."""
        return self._service.get_usage(name)


class ExperimentAPI:
    """Experiment operations API."""

    def __init__(self):
        # Lazy import to avoid circular dependencies
        from adare.services import experiment_service
        self._service = experiment_service.ExperimentService()

    def create(self, request):
        """Create a new experiment."""
        return self._service.create(request)

    def load(self, request):
        """Load an experiment."""
        return self._service.load(request)

    def clone(self, request):
        """Clone an experiment."""
        return self._service.clone(request)

    def remove(self, request):
        """Remove an experiment."""
        return self._service.remove(request)

    def clean(self, project_path, name):
        """Clean experiment build artifacts."""
        return self._service.clean(project_path, name)

    def example(self, project_path, name):
        """Create example experiment."""
        return self._service.example(project_path, name)

    def test(self, project_path, name, environment_name):
        """Test experiment."""
        return self._service.test(project_path, name, environment_name)

    def add_environments(self, request):
        """Add environments to experiment."""
        return self._service.add_environments(request)

    def remove_environments(self, request):
        """Remove environments from experiment."""
        return self._service.remove_environments(request)

    def list_all(self, project_path):
        """List all experiments."""
        return self._service.list_all(project_path)

    def get_by_name(self, project_path, name):
        """Get experiment by name."""
        return self._service.get_by_name(project_path, name)

    def get_by_id(self, project_path, experiment_id):
        """Get experiment by ID."""
        return self._service.get_by_id(project_path, experiment_id)


class ManageAPI:
    """Database and system management API."""

    def __init__(self):
        # Lazy import to avoid circular dependencies
        from adare.services import manage_service
        self._service = manage_service.ManageService()

    def get_db_status(self):
        """Check database system status."""
        return self._service.get_db_status()

    def init_db(self):
        """Initialize the database system."""
        return self._service.init_db()

    def repair_db(self):
        """Repair the database system."""
        return self._service.repair_db()

    def clean_install_db(self, force=False):
        """Perform clean database installation."""
        return self._service.clean_install_db(force=force)

    def reset_db(self):
        """Reset the database."""
        return self._service.reset_db()

    def reset_all_vms(self, force=False):
        """Reset all VMs."""
        return self._service.reset_all_vms(force=force)

    def refresh_vm_runtime(self, project_path=None):
        """Refresh VM runtime."""
        return self._service.refresh_vm_runtime(project_path=project_path)

    def build_vm_runtime_wheels(self, project_path=None):
        """Build VM runtime wheels."""
        return self._service.build_vm_runtime_wheels(project_path=project_path)


class EnvironmentAPI:
    """Environment configuration API."""

    def __init__(self):
        # Lazy import to avoid circular dependencies
        from adare.services import environment_service
        self._service = environment_service.EnvironmentService()

    def load(self, request):
        """Load an environment."""
        return self._service.load(request)

    def create(self, request):
        """Create a new environment."""
        return self._service.create(request)

    def delete(self, identifier, force=False):
        """Delete an environment."""
        return self._service.delete(identifier, force=force)

    def list_all(self):
        """List all environments."""
        return self._service.list_all()

    def get_by_id(self, ulid):
        """Get environment by ID."""
        return self._service.get_by_id(ulid)

    def get_by_name(self, name):
        """Get environment by name."""
        return self._service.get_by_name(name)


class ProjectAPI:
    """Project management API."""

    def __init__(self):
        # Lazy import to avoid circular dependencies
        from adare.services import project_service
        self._service = project_service.ProjectService()

    def create(self, request):
        """Create a new project."""
        return self._service.create(request)

    def remove(self, request):
        """Remove a project."""
        return self._service.remove(request)

    def list_all(self):
        """List all projects."""
        return self._service.list_all()

    def get_by_path(self, path):
        """Get project by path."""
        return self._service.get_by_path(path)


class ShowAPI:
    """Data retrieval and display API."""

    def __init__(self):
        # Lazy import to avoid circular dependencies
        from adare.services import show_service
        self._service = show_service.ShowService()

    def list_runs(self, request=None):
        """List all runs."""
        return self._service.list_runs(request)

    def get_run(self, ulid=None, latest_in_project=False, project_path=None):
        """Get run details."""
        return self._service.get_run(ulid=ulid, latest_in_project=latest_in_project, project_path=project_path)

    def remove_run(self, request):
        """Remove a run."""
        return self._service.remove_run(request)

    def list_projects(self):
        """List all projects."""
        return self._service.list_projects()

    def list_environments(self):
        """List all environments."""
        return self._service.list_environments()

    def get_environment(self, name):
        """Get environment details."""
        return self._service.get_environment(name)

    def list_experiments(self):
        """List all experiments."""
        return self._service.list_experiments()

    def get_experiment(self, name=None, ulid=None, dotnotation=None):
        """Get experiment details."""
        return self._service.get_experiment(name=name, ulid=ulid, dotnotation=dotnotation)

    def list_testfunctions(self, file_name=None):
        """List all testfunctions."""
        return self._service.list_testfunctions(file_name=file_name)

    def get_testfunction(self, dotnotation):
        """Get testfunction details."""
        return self._service.get_testfunction(dotnotation)


class VMAPI:
    """Virtual machine operations API."""

    def __init__(self):
        # Lazy import to avoid circular dependencies
        from adare.services import vm_service
        self._service = vm_service.VMService()

    def load(self, request):
        """Load a VM from file."""
        return self._service.load(request)

    def list_all(self):
        """List all VMs."""
        return self._service.list_all()

    def get_by_id(self, vm_id):
        """Get VM by ID."""
        return self._service.get_by_id(vm_id)

    def get_by_name(self, name):
        """Get VM by name."""
        return self._service.get_by_name(name)

    def delete(self, vm_id, force=False):
        """Delete a VM."""
        return self._service.delete(vm_id, force=force)

    def clear_all(self, force=False):
        """Clear all VMs."""
        return self._service.clear_all(force=force)

    def clear_by_environment(self, environment_ulid, force=False):
        """Clear VMs by environment."""
        return self._service.clear_by_environment(environment_ulid, force=force)

    def list_instances(self, vm_id=None):
        """List VM instances."""
        return self._service.list_instances(vm_id=vm_id)

    def get_instance_by_id(self, instance_id):
        """Get VM instance by ID."""
        return self._service.get_instance_by_id(instance_id)

    async def remove_instance(self, instance_id):
        """Remove a VM instance (async)."""
        return await self._service.remove_instance(instance_id)

    async def remove_all_stopped_instances(self):
        """Remove all stopped VM instances (async)."""
        return await self._service.remove_all_stopped_instances()

    def get_instance_usage(self):
        """Get VM instance usage."""
        return self._service.get_instance_usage()

    async def test_ova(self, request):
        """Test an OVA file (async)."""
        return await self._service.test_ova(request)


class WebAPI:
    """Web integration and sync API."""

    def __init__(self):
        # Lazy import to avoid circular dependencies
        from adare.services import web_service
        self._service = web_service.WebService()

    def login(self):
        """Login to web service."""
        return self._service.login()

    def logout(self):
        """Logout from web service."""
        return self._service.logout()

    def get_status(self):
        """Get web service status."""
        return self._service.get_status()

    def download_environment(self, request):
        """Download environment from web."""
        return self._service.download_environment(request)

    def download_experiment(self, request):
        """Download experiment from web."""
        return self._service.download_experiment(request)

    def download_testfunction(self, request):
        """Download testfunction from web."""
        return self._service.download_testfunction(request)

    def sync(self, request=None):
        """Sync with web service."""
        return self._service.sync(request)

    def upload_run(self, request):
        """Upload run to web."""
        return self._service.upload_run(request)

    def publish_run(self, request):
        """Publish run to web."""
        return self._service.publish_run(request)

    def check_experiment(self, request):
        """Check experiment on web."""
        return self._service.check_experiment(request)

    def check_run(self, request):
        """Check run on web."""
        return self._service.check_run(request)


class AdareAPI:
    """
    Main ADARE API facade.

    Provides unified API interface for web and CLI frontends.

    Available facades:
    - api.devmode - Development mode operations
    - api.testfunction - Test function management
    - api.experiment - Experiment lifecycle operations
    - api.manage - Database and system management
    - api.environment - Environment configuration
    - api.project - Project management
    - api.show - Data retrieval and display
    - api.vm - Virtual machine operations
    - api.web - Web integration and sync
    """

    def __init__(self):
        self.devmode = DevModeAPI()
        self.testfunction = TestFunctionAPI()
        self.experiment = ExperimentAPI()
        self.manage = ManageAPI()
        self.environment = EnvironmentAPI()
        self.project = ProjectAPI()
        self.show = ShowAPI()
        self.vm = VMAPI()
        self.web = WebAPI()

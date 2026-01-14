"""
ADARE API Facade - Single entry point for all ADARE operations.

This facade provides a unified API that can be used by any frontend:
- CLI (current)
- Web UI (planned)
- REST API (future)

Usage:
    from adare.api import AdareAPI
    from adare.core.dto.project import ProjectCreateRequest
    from adare.core.dto.environment import EnvironmentLoadRequest

    api = AdareAPI()

    # Create a project
    result = api.project.create(ProjectCreateRequest(
        name="my-project",
        path=Path("/path/to/project"),
        description="My project description"
    ))

    # Load an environment
    result = api.environment.load(EnvironmentLoadRequest(
        environment="/path/to/env.yml"
    ))

    if result.success:
        print(f"Success: {result.data}")
    else:
        print(f"Error: {result.error.message}")
"""
from adare.services.project_service import ProjectService
from adare.services.environment_service import EnvironmentService
from adare.services.vm_service import VMService
from adare.services.experiment_service import ExperimentService
from adare.services.testfunction_service import TestfunctionService
from adare.services.manage_service import ManageService
from adare.services.show_service import ShowService
from adare.services.web_service import WebService
from adare.services.devmode_service import DevModeService


class AdareAPI:
    """
    Main API facade for ADARE.

    Provides access to all domain services through a single entry point.
    Each service handles its own business logic and returns Result[T] objects.

    Attributes:
        project: ProjectService for project management operations
        environment: EnvironmentService for environment management operations
        vm: VMService for VM and instance management operations
        experiment: ExperimentService for experiment management operations
        testfunction: TestfunctionService for testfunction management operations
        manage: ManageService for database and system management operations
        show: ShowService for data display operations
        web: WebService for web-related operations
        devmode: DevModeService for development mode operations
    """

    def __init__(self):
        """Initialize the API with all available services."""
        self._project = ProjectService()
        self._environment = EnvironmentService()
        self._vm = VMService()
        self._experiment = ExperimentService()
        self._testfunction = TestfunctionService()
        self._manage = ManageService()
        self._show = ShowService()
        self._web = WebService()
        self._devmode = DevModeService()

    @property
    def project(self) -> ProjectService:
        """Access project management operations."""
        return self._project

    @property
    def environment(self) -> EnvironmentService:
        """Access environment management operations."""
        return self._environment

    @property
    def vm(self) -> VMService:
        """Access VM and instance management operations."""
        return self._vm

    @property
    def experiment(self) -> ExperimentService:
        """Access experiment management operations."""
        return self._experiment

    @property
    def testfunction(self) -> TestfunctionService:
        """Access testfunction management operations."""
        return self._testfunction

    @property
    def manage(self) -> ManageService:
        """Access database and system management operations."""
        return self._manage

    @property
    def show(self) -> ShowService:
        """Access data display operations."""
        return self._show

    @property
    def web(self) -> WebService:
        """Access web-related operations."""
        return self._web

    @property
    def devmode(self) -> DevModeService:
        """Access development mode operations."""
        return self._devmode

"""DataRetrievalApi composing all query mixins."""

from adare.database.api.frontend._base import DataRetrievalBase
from adare.database.api.frontend.experiment_queries import ExperimentQueryMixin
from adare.database.api.frontend.project_queries import ProjectQueryMixin
from adare.database.api.frontend.run_queries import RunQueryMixin
from adare.database.api.frontend.test_queries import TestQueryMixin


class DataRetrievalApi(
    DataRetrievalBase,
    ProjectQueryMixin,
    ExperimentQueryMixin,
    RunQueryMixin,
    TestQueryMixin,
):
    """
    Unified API for retrieving data from both global and project databases.

    This API provides access to:
    - Global models: Project, Environment, VM, TestFunction (from global database)
    - Project models: Experiment, ExperimentRun (from project-specific database)

    Composed from domain-specific mixins:
    - DataRetrievalBase: Initialization, context management, validation, display helpers
    - ProjectQueryMixin: Project and environment queries
    - ExperimentQueryMixin: Experiment queries
    - RunQueryMixin: Experiment run queries
    - TestQueryMixin: Test and testfunction queries
    """

    pass

************************
Testing Architecture
************************

ADARE follows a comprehensive testing strategy that ensures all implemented methods and classes have meaningful test coverage, as mandated by the project's testing guidelines.

Overview
========

The testing architecture is designed to provide:

- **100% Coverage Requirement**: All implemented methods and classes must have meaningful tests
- **Layered Testing Strategy**: Unit tests, integration tests, and end-to-end tests
- **Mock-Based Testing**: Extensive use of mocks for external dependencies
- **Async Testing Support**: Full support for testing async/await patterns
- **Database Testing**: Isolated database testing with temporary databases

Testing Guidelines
==================

Core Principles
---------------

According to CLAUDE.md testing requirements:

.. code-block:: text

   "for all implemented methods and classes build also meaningful tests"

This means:

- Every public method must have at least one test
- Every class must have tests for its core functionality
- Critical business logic must have comprehensive test coverage
- Error handling and edge cases must be tested
- External dependencies must be mocked appropriately

Test Organization
=================

Directory Structure
-------------------

Tests are organized in the ``adare/tests/`` directory following this structure:

.. code-block:: text

   adare/tests/
   ├── test_backend_experiment_commands.py     # Backend experiment operations
   ├── test_backend_experiment_runner.py       # Modern async experiment runner
   ├── test_cli_experiment.py                  # CLI experiment commands
   ├── test_database_api_experiment.py         # Database API operations
   ├── test_database_models_experiment.py      # Database model tests
   ├── test_show_commands.py                   # Show/list command tests
   ├── test_websocket_action_controller.py     # WebSocket functionality
   ├── test_yaml_*.py                          # YAML processing tests
   └── ...

Naming Convention
-----------------

Test files follow the naming pattern: ``test_<module_path>.py``

Examples:
- ``adare/backend/experiment/commands.py`` → ``test_backend_experiment_commands.py``
- ``adare/cli/experiment.py`` → ``test_cli_experiment.py``
- ``adare/database/api/experiment.py`` → ``test_database_api_experiment.py``

Testing Categories
==================

Unit Tests
----------

Test individual functions and methods in isolation:

.. code-block:: python

   def test_experiment_creation():
       """Test basic experiment creation functionality."""
       config = ExperimentConfig(
           project_path=Path("/test/project"),
           experiment_name="test_experiment",
           environment_name="test_environment"
       )
       assert config.experiment_name == "test_experiment"

Integration Tests
-----------------

Test interactions between components:

.. code-block:: python

   @patch('adare.backend.experiment.commands.experiment_database')
   @patch('adare.backend.experiment.commands.environment_database')
   def test_experiment_run_integration(self, mock_env_db, mock_exp_db):
       """Test complete experiment run workflow."""
       # Setup mocks and test full workflow
       pass

Async Tests
-----------

Test async/await functionality:

.. code-block:: python

   @pytest.mark.asyncio
   async def test_async_experiment_execution():
       """Test async experiment execution patterns."""
       result = await run_experiment(config)
       assert result is not None

Database Tests
--------------

Test database operations with temporary databases:

.. code-block:: python

   @pytest.fixture
   def temp_db_path():
       """Create temporary database for testing."""
       temp_dir = tempfile.mkdtemp()
       db_path = Path(temp_dir) / "test.db"
       yield db_path
       shutil.rmtree(temp_dir)

Mock Strategies
===============

External Dependencies
---------------------

All external dependencies are mocked to ensure isolated testing:

.. code-block:: python

   @patch('adare.backend.experiment.commands.VirtualBoxVM')
   @patch('adare.backend.experiment.commands.WebSocketClient')
   def test_vm_integration(self, mock_ws_client, mock_vm):
       """Test VM integration with mocked dependencies."""
       pass

Database Mocking
----------------

Database operations use temporary databases or mocks:

.. code-block:: python

   @pytest.fixture
   def experiment_api(temp_db_path):
       """Create ExperimentApi with temporary database."""
       return ExperimentApi(temp_db_path)

File System Mocking
-------------------

File system operations are mocked for predictable testing:

.. code-block:: python

   @patch('adare.backend.experiment.commands.ExperimentDirectory')
   def test_experiment_directory_operations(self, mock_exp_dir):
       """Test experiment directory operations."""
       pass

Error Testing
=============

Exception Handling
------------------

All error conditions must be tested:

.. code-block:: python

   def test_experiment_not_found_error():
       """Test handling when experiment is not found."""
       with pytest.raises(ExperimentDirectoryDoesNotExistError):
           experiment_load("nonexistent_experiment", "test_project")

Logging Verification
--------------------

Critical operations verify proper logging:

.. code-block:: python

   @patch('adare.cli.experiment.log')
   def test_keyboard_interrupt_logging(self, mock_log):
       """Test that keyboard interrupt is properly logged."""
       # Test keyboard interrupt handling
       mock_log.info.assert_called_with("Keyboard interrupt received, shutting down gracefully...")

Test Coverage Status
====================

Current Coverage
----------------

As of the latest audit:

- **Total Modules**: ~150+ Python files
- **Modules with Tests**: ~20 files
- **Test Coverage**: ~15% of critical business logic modules

Priority Areas
--------------

**High Priority (Missing Tests)**:

1. Backend command modules
2. CLI interface modules  
3. Database API modules
4. Core type definitions

**Medium Priority**:

1. Helper function modules
2. Configuration modules
3. Directory management

**Low Priority**:

1. Frontend/UI components
2. Integration modules
3. Utility functions

Running Tests
=============

Basic Test Execution
--------------------

.. code-block:: bash

   # Run all tests
   poetry run pytest
   
   # Run specific test file
   poetry run pytest adare/tests/test_backend_experiment_commands.py
   
   # Run with verbose output
   poetry run pytest -v
   
   # Run tests matching pattern
   poetry run pytest -k "experiment"

Coverage Reporting
------------------

.. code-block:: bash

   # Run tests with coverage
   poetry run pytest --cov=adare
   
   # Generate HTML coverage report
   poetry run pytest --cov=adare --cov-report=html

Async Test Execution
--------------------

Async tests use the ``pytest-asyncio`` plugin:

.. code-block:: bash

   # Run async tests specifically
   poetry run pytest -m asyncio

Best Practices
==============

Test Design
-----------

1. **Arrange-Act-Assert Pattern**: Structure tests clearly
2. **Single Responsibility**: Each test should test one thing
3. **Descriptive Names**: Test names should describe what they test
4. **Mock External Dependencies**: Never rely on external systems
5. **Test Error Conditions**: Always test failure scenarios

Fixture Design
--------------

1. **Reusable Fixtures**: Create fixtures for common test data
2. **Scoped Appropriately**: Use correct fixture scope (function, class, module)
3. **Clean Isolation**: Each test should be independent

Documentation
-------------

1. **Docstrings Required**: All test modules need descriptive docstrings
2. **Test Purpose Clear**: Each test should have clear documentation
3. **Setup Instructions**: Complex tests need setup documentation

Continuous Improvement
======================

The testing architecture is continuously improved through:

1. **Regular Coverage Audits**: Identifying gaps in test coverage
2. **Refactoring Tests**: Improving test maintainability
3. **Adding Integration Tests**: Expanding beyond unit tests
4. **Performance Testing**: Adding performance regression tests

This testing architecture ensures the reliability and maintainability of the ADARE framework while supporting rapid development and confident refactoring.
"""
Tests for output formatter functionality.
"""
import json
import yaml
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, Any

import pytest
import attrs

from adare.helperfunctions.output_formatter import (
    OutputFormat, StructuredOutputFormatter, OutputFormatter, get_formatter
)
from adare.backend.experiment.batch_runner import ExperimentResult, BatchRunSummary
from adarelib.constants import StatusEnum


@dataclass
class TestDataClass:
    """Test dataclass for serialization."""
    name: str
    value: int
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'value': self.value,
            'timestamp': self.timestamp.isoformat()
        }


@attrs.define
class TestAttrsClass:
    """Test attrs class for serialization."""
    title: str
    count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'title': self.title,
            'count': self.count
        }


class TestStructuredOutputFormatter:
    """Test the StructuredOutputFormatter class."""

    def setup_method(self):
        self.formatter = StructuredOutputFormatter()

    def test_prepare_basic_types(self):
        """Test preparation of basic data types."""
        assert self.formatter.prepare_data("text") == "text"
        assert self.formatter.prepare_data(42) == 42
        assert self.formatter.prepare_data(3.14) == 3.14
        assert self.formatter.prepare_data(True) is True
        assert self.formatter.prepare_data(None) is None

    def test_prepare_datetime(self):
        """Test datetime preparation."""
        dt = datetime(2024, 1, 1, 12, 0, 0)
        result = self.formatter.prepare_data(dt)
        assert result == "2024-01-01T12:00:00"

    def test_prepare_timedelta(self):
        """Test timedelta preparation."""
        td = timedelta(seconds=65)
        result = self.formatter.prepare_data(td)
        assert result == 65.0

    def test_strip_rich_markup(self):
        """Test Rich markup removal."""
        text_with_markup = "[bold]Hello[/bold] [red]World[/red] :check_mark:"
        result = self.formatter._strip_rich_markup(text_with_markup)
        assert result == "Hello World"

    def test_prepare_dataclass(self):
        """Test dataclass preparation."""
        dt = datetime(2024, 1, 1, 12, 0, 0)
        test_obj = TestDataClass("test", 42, dt)
        result = self.formatter.prepare_data(test_obj)

        expected = {
            'name': 'test',
            'value': 42,
            'timestamp': '2024-01-01T12:00:00'
        }
        assert result == expected

    def test_prepare_attrs_class(self):
        """Test attrs class preparation."""
        test_obj = TestAttrsClass("example", 5)
        result = self.formatter.prepare_data(test_obj)

        expected = {
            'title': 'example',
            'count': 5
        }
        assert result == expected

    def test_prepare_list(self):
        """Test list preparation."""
        test_list = ["text", 42, datetime(2024, 1, 1)]
        result = self.formatter.prepare_data(test_list)

        expected = ["text", 42, "2024-01-01T00:00:00"]
        assert result == expected

    def test_prepare_dict(self):
        """Test dictionary preparation."""
        test_dict = {
            "name": "test",
            "timestamp": datetime(2024, 1, 1),
            "nested": {"value": 42}
        }
        result = self.formatter.prepare_data(test_dict)

        expected = {
            "name": "test",
            "timestamp": "2024-01-01T00:00:00",
            "nested": {"value": 42}
        }
        assert result == expected

    def test_serialize_json(self):
        """Test JSON serialization."""
        data = {"name": "test", "value": 42}
        result = self.formatter.serialize_json(data)

        # Parse back to verify valid JSON
        parsed = json.loads(result)
        assert parsed == data

    def test_serialize_yaml(self):
        """Test YAML serialization."""
        data = {"name": "test", "value": 42}
        result = self.formatter.serialize_yaml(data)

        # Parse back to verify valid YAML
        parsed = yaml.safe_load(result)
        assert parsed == data


class TestOutputFormatter:
    """Test the main OutputFormatter class."""

    def test_rich_format(self):
        """Test Rich format returns data as-is."""
        formatter = OutputFormatter(OutputFormat.RICH)
        data = "test data"
        result = formatter.format(data)
        assert result == data

    def test_json_format(self):
        """Test JSON format."""
        formatter = OutputFormatter(OutputFormat.JSON)
        data = {"name": "test", "value": 42}
        result = formatter.format(data)

        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed == data

    def test_yaml_format(self):
        """Test YAML format."""
        formatter = OutputFormatter(OutputFormat.YAML)
        data = {"name": "test", "value": 42}
        result = formatter.format(data)

        # Should be valid YAML
        parsed = yaml.safe_load(result)
        assert parsed == data

    def test_get_formatter_factory(self):
        """Test the get_formatter factory function."""
        # Test enum input
        formatter = get_formatter(OutputFormat.JSON)
        assert formatter.format_type == OutputFormat.JSON

        # Test string input
        formatter = get_formatter("yaml")
        assert formatter.format_type == OutputFormat.YAML

        # Test invalid input (should default to Rich)
        formatter = get_formatter("invalid")
        assert formatter.format_type == OutputFormat.RICH


class TestExperimentDataModels:
    """Test the experiment data models' to_dict methods."""

    def test_experiment_result_to_dict(self):
        """Test ExperimentResult to_dict method."""
        start_time = datetime(2024, 1, 1, 12, 0, 0)
        end_time = datetime(2024, 1, 1, 12, 5, 0)
        duration = timedelta(minutes=5)

        result = ExperimentResult(
            environment="test_env",
            experiment="test_exp",
            status=StatusEnum.SUCCESS,
            duration=duration,
            error_message=None,
            run_ulid="test_ulid",
            start_time=start_time,
            end_time=end_time
        )

        result_dict = result.to_dict()

        assert result_dict['environment'] == "test_env"
        assert result_dict['experiment'] == "test_exp"
        assert result_dict['status'] == "SUCCESS"
        assert result_dict['duration_seconds'] == 300.0  # 5 minutes
        assert result_dict['run_ulid'] == "test_ulid"
        assert result_dict['start_time'] == "2024-01-01T12:00:00"
        assert result_dict['end_time'] == "2024-01-01T12:05:00"

    def test_batch_run_summary_to_dict(self):
        """Test BatchRunSummary to_dict method."""
        duration = timedelta(minutes=10)

        # Create test results
        result1 = ExperimentResult(
            environment="env1",
            experiment="exp1",
            status=StatusEnum.SUCCESS,
            duration=timedelta(minutes=5)
        )

        result2 = ExperimentResult(
            environment="env2",
            experiment="exp2",
            status=StatusEnum.FAILED,
            duration=timedelta(minutes=3),
            error_message="Test error"
        )

        summary = BatchRunSummary(
            results=[result1, result2],
            total_combinations=2,
            total_duration=duration
        )

        summary_dict = summary.to_dict()

        assert summary_dict['summary']['total_combinations'] == 2
        assert summary_dict['summary']['successful_runs'] == 1
        assert summary_dict['summary']['failed_runs'] == 1
        assert summary_dict['summary']['success_rate'] == 50.0
        assert summary_dict['summary']['total_duration_seconds'] == 600.0  # 10 minutes

        assert len(summary_dict['results']) == 2
        assert summary_dict['results'][0]['status'] == "SUCCESS"
        assert summary_dict['results'][1]['status'] == "FAILED"
        assert summary_dict['results'][1]['error_message'] == "Test error"


if __name__ == "__main__":
    pytest.main([__file__])
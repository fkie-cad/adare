from datetime import datetime

import pytest

pytestmark = pytest.mark.unit

from adare.core.dto.show import (
    RunDetail,
    RunListItem,
    RunListRequest,
    RunRemoveResult,
)


class TestRunListRequest:
    def test_defaults(self):
        req = RunListRequest()
        assert req.project is None
        assert req.environment is None
        assert req.experiment is None

    def test_with_filters(self):
        req = RunListRequest(project="p", environment="e", experiment="x")
        assert req.project == "p"


class TestRunListItem:
    def test_construction(self):
        item = RunListItem(
            ulid="abc", experiment_name="exp",
            experiment_ulid="e1", environment_name="env",
            environment_ulid="v1", project_name="proj",
        )
        assert item.status == ""
        assert item.published is False
        assert item.fake is False

    def test_to_dict(self):
        now = datetime(2025, 1, 1, 12, 0, 0)
        item = RunListItem(
            ulid="abc", experiment_name="exp",
            experiment_ulid="e1", environment_name="env",
            environment_ulid="v1", project_name="proj",
            start_time=now, duration_seconds=60.0,
            status="SUCCESS",
        )
        d = item.to_dict()
        assert d["ulid"] == "abc"
        assert d["experiment"]["name"] == "exp"
        assert d["timing"]["start_time"] == "2025-01-01T12:00:00"
        assert d["status"] == "SUCCESS"


class TestRunDetail:
    def test_construction(self):
        detail = RunDetail(
            ulid="abc", experiment_name="exp",
            experiment_ulid="e1", environment_name="env",
            environment_ulid="v1", project_name="proj",
        )
        assert detail.test_results == []
        assert detail.os_info == ""


class TestRunRemoveResult:
    def test_construction(self):
        r = RunRemoveResult(removed=True, ulid="abc", was_fake=True)
        assert r.removed is True
        assert r.was_fake is True

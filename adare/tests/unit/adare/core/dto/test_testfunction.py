import pytest
from pathlib import Path

pytestmark = pytest.mark.unit

from adare.core.dto.testfunction import (
    TestfunctionCreateRequest, TestfunctionInfo, TestfunctionListItem,
    TestfunctionRemoveResult, TestfunctionExistsResult,
)


class TestTestfunctionCreateRequest:
    def test_construction(self):
        req = TestfunctionCreateRequest(project_path=Path("/p"), name="tf1")
        assert req.name == "tf1"


class TestTestfunctionInfo:
    def test_defaults(self):
        info = TestfunctionInfo(id="1", name="tf", file_path=Path("/f"))
        assert info.is_published is False
        assert info.usage_count == 0
        assert info.experiments_using == []
        assert info.next_steps == []

    def test_full_construction(self):
        info = TestfunctionInfo(
            id="1", name="tf", file_path=None,
            is_published=True, remote_url="http://x",
            usage_count=5, experiments_using=["e1"],
        )
        assert info.is_published is True
        assert info.file_path is None


class TestTestfunctionListItem:
    def test_construction(self):
        item = TestfunctionListItem(id="1", name="tf", dotnotation="a.b.tf")
        assert item.dotnotation == "a.b.tf"
        assert item.is_published is False


class TestTestfunctionRemoveResult:
    def test_construction(self):
        r = TestfunctionRemoveResult(name="tf", was_removed=True, experiments_affected=2)
        assert r.was_removed is True
        assert r.runs_deleted == 0


class TestTestfunctionExistsResult:
    def test_construction(self):
        r = TestfunctionExistsResult(name="tf", exists=True)
        assert r.exists is True

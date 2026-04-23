from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit

from adare.core.dto.project import ProjectCreateRequest, ProjectInfo, ProjectListItem, ProjectRemoveRequest


class TestProjectCreateRequest:
    def test_construction(self):
        req = ProjectCreateRequest(name="myproj", path=Path("/tmp/proj"))
        assert req.name == "myproj"
        assert req.path == Path("/tmp/proj")
        assert req.description == ""

    def test_with_description(self):
        req = ProjectCreateRequest(name="p", path=Path("/x"), description="desc")
        assert req.description == "desc"


class TestProjectRemoveRequest:
    def test_construction(self):
        req = ProjectRemoveRequest(path=Path("/tmp/proj"))
        assert req.path == Path("/tmp/proj")


class TestProjectInfo:
    def test_construction(self):
        info = ProjectInfo(id="abc", name="proj", path=Path("/p"), description="d")
        assert info.id == "abc"
        assert info.next_steps == []
        assert info.tip is None

    def test_to_dict(self):
        info = ProjectInfo(id="1", name="n", path=Path("/p"), description="d", tip="t")
        d = info.to_dict()
        assert d["id"] == "1"
        assert d["path"] == "/p"
        assert d["tip"] == "t"


class TestProjectListItem:
    def test_construction(self):
        item = ProjectListItem(id="1", name="p", path=Path("/p"), description="d")
        assert item.experiment_count == 0

    def test_to_dict(self):
        item = ProjectListItem(id="1", name="p", path=Path("/p"), description="d", experiment_count=3)
        d = item.to_dict()
        assert d["experiment_count"] == 3
        assert d["path"] == "/p"

    def test_from_model(self):
        model = MagicMock()
        model.id = "uid"
        model.name = "proj"
        model.path = "/data/proj"
        model.description = "a project"
        item = ProjectListItem.from_model(model)
        assert item.id == "uid"
        assert item.path == Path("/data/proj")
        assert item.description == "a project"

    def test_from_model_no_description(self):
        model = MagicMock()
        model.id = "uid"
        model.name = "proj"
        model.path = "/data/proj"
        model.description = None
        item = ProjectListItem.from_model(model)
        assert item.description == ""

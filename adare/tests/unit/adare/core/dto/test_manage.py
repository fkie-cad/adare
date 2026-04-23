import pytest
from pathlib import Path

pytestmark = pytest.mark.unit

from adare.core.dto.manage import DbStatusResult, DbInitResult, DbRepairResult, VmResetResult


class TestDbStatusResult:
    def test_healthy_db(self):
        r = DbStatusResult(
            global_db_exists=True, global_db_accessible=True,
            global_db_location=Path("/db"), valid=True,
        )
        assert r.valid is True
        assert r.errors == []

    def test_unhealthy_db(self):
        r = DbStatusResult(
            global_db_exists=False, global_db_accessible=False,
            global_db_location=None, valid=False,
            errors=["Database not found"],
        )
        assert r.valid is False
        assert len(r.errors) == 1


class TestDbInitResult:
    def test_construction(self):
        r = DbInitResult(
            global_db_initialized=True,
            global_db_location=Path("/db/global.db"),
        )
        assert r.global_db_initialized is True
        assert r.errors == []


class TestDbRepairResult:
    def test_construction(self):
        r = DbRepairResult(repaired=True, actions_taken=["Fixed schema"])
        assert r.repaired is True
        assert r.actions_taken == ["Fixed schema"]


class TestVmResetResult:
    def test_construction(self):
        r = VmResetResult(
            deleted_count=2, failed_count=1,
            deleted_vms=["vm1", "vm2"], failed_vms=["vm3"],
        )
        assert r.deleted_count == 2
        assert len(r.failed_vms) == 1

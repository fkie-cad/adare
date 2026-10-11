"""Tests for resolving a testfunction dotnotation to its id (``adare test info``)."""

from types import SimpleNamespace

import pytest
import ulid
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from adare.database.api.frontend.test_queries import TestQueryMixin
from adare.database.models.global_models import GlobalBase, TestFunction, TestFunctionFile
from adare.exceptions import TestFunctionNotFoundError

pytestmark = pytest.mark.unit


@pytest.fixture()
def resolver(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'global.db').as_posix()}")
    GlobalBase.metadata.create_all(engine)
    session = Session(engine)
    # Files are stored by stem, exactly as create_testfunction_file_obj does.
    tf_file = TestFunctionFile(id=str(ulid.ULID()), name='standard', path='/tf/standard/standard.py', sha256hash='f')
    session.add(tf_file)
    session.flush()
    tf = TestFunction(id=str(ulid.ULID()), type='standard', name='file_exists', sha256hash='a', file_id=tf_file.id)
    session.add(tf)
    session.flush()
    mixin = TestQueryMixin()
    mixin._global_api = SimpleNamespace(_session=session)
    yield mixin, tf.id
    session.close()


@pytest.mark.parametrize('dotnotation', ['standard.file_exists', 'myproj.standard.file_exists'])
def test_resolves_stem_stored_file(resolver, dotnotation):
    mixin, expected_id = resolver
    assert mixin.testfunction_dotnotation_to_id(dotnotation) == expected_id


@pytest.mark.parametrize('dotnotation', ['standard.missing', 'nofile.file_exists'])
def test_unknown_raises_not_found(resolver, dotnotation):
    mixin, _ = resolver
    with pytest.raises(TestFunctionNotFoundError):
        mixin.testfunction_dotnotation_to_id(dotnotation)

"""Nested events store the enclosing action's key in Event.parent_group_id, never in parent_event_id."""

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from adare.database.api.event import EventDbApi
from adare.database.api.frontend._base import DataRetrievalBase
from adare.database.models.project_models import ActionEvent, ExperimentRun, ProjectBase, TestEvent

pytestmark = pytest.mark.unit

RUN = 'run-1'


@pytest.fixture
def api(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'project.sqlite3'}")
    ProjectBase.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add(ExperimentRun(id=RUN, fake=False, published=False))
    session.commit()
    # Bypass the constructor: it locates the project database by run id.
    event_api = EventDbApi.__new__(EventDbApi)
    event_api._session = session
    yield event_api
    session.close()
    engine.dispose()


def test_action_event_stores_the_parent_key_as_group(api):
    api.add_action_event({'event_type': 'click_start'}, 'find_step_1', RUN, 'action_0_click_1')
    api.add_action_event({'event_type': 'click_start'}, 'action_0_click_1', RUN)

    rows = {e.event_group_id: e for e in api._session.query(ActionEvent).all()}
    assert rows['find_step_1'].parent_group_id == 'action_0_click_1'
    assert rows['action_0_click_1'].parent_group_id is None
    assert all(e.parent_event_id is None for e in rows.values())


def test_test_event_stores_the_parent_key_as_group(api):
    api.add_test_event({'event_type': 'test_start', 'test_name': 't'}, 'test_1', RUN, 'action_2_test_1')

    event = api._session.query(TestEvent).one()
    assert event.parent_group_id == 'action_2_test_1'
    assert event.parent_event_id is None


@pytest.mark.parametrize(('parent_group_id', 'level'), [(None, 0), ('', 0), ('action_0_click_1', 1)])
def test_display_level_comes_from_the_group_without_a_query(parent_group_id, level):
    event = SimpleNamespace(parent_group_id=parent_group_id)
    assert DataRetrievalBase._compute_display_level(event) == level

# external imports
from sqlalchemy import Table, ForeignKey, Column, Integer, DateTime, Boolean, String
from sqlalchemy.orm import registry, relationship
from attrs import define
from datetime import datetime
from typing import List

# configure logging
import logging
log = logging.getLogger(__name__)


mapper_registry = registry()
Base = mapper_registry.generate_base()


@mapper_registry.mapped
class MappingTestfunctionToTestoption:
    __table__ = Table(
        'TestfunctionToTestoption',
        mapper_registry.metadata,
        Column("id_testfunction", ForeignKey("testfunction.id"), primary_key=True),
        Column("id_testoption", ForeignKey("testoption.id"), primary_key=True)
    )


@mapper_registry.mapped
class MappingTestToTestoption:
    __table__ = Table(
        'TestToTestoption',
        mapper_registry.metadata,
        Column("id_test", ForeignKey("test.id"), primary_key=True),
        Column("id_testoption", ForeignKey("testoption.id"), primary_key=True)
    )


@mapper_registry.mapped
@define(slots=False)
class Test:
    __table__ = Table(
        'test',
        mapper_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('experiment', Integer, ForeignKey('experiment.id')),
        Column('name', String),
        Column('description', String),
        Column('inputfile', String),
        Column('result', Integer, ForeignKey('testresult.id')),
        Column('details', String),
    )
    experiment = int
    name: str
    function: int
    description: str
    inputfile: str
    result: int
    details: str
    options: list

    __mapper_args__ = {
        'properties': {
            'options': relationship('Testoption', secondary=MappingTestToTestoption.__table__, backref='tests')
        }
    }


@mapper_registry.mapped
@define(slots=False)
class Experiment:
    __table__ = Table(
        'experiment',
        mapper_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('start_timestamp', DateTime),
        Column('end_timestamp', DateTime),
        Column('success', Boolean),
        Column('success_post_setup_installations', Boolean),
        Column('success_gui_automation', Boolean),
        Column('success_mount_networkdrives', Boolean),
        Column('success_parse_and_test', Boolean)
    )
    start_timestamp: datetime
    end_timestamp: datetime
    success: bool
    success_post_setup_installations: bool
    success_gui_automation: bool
    success_mount_networkdrives: bool
    tests: List[Test]

    __mapper_args__ = {
        'properties': {
            'tests': relationship('Test')
        }
    }


@mapper_registry.mapped
@define(slots=False)
class Testfunction:
    __table__ = Table(
        'testfunction',
        mapper_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('name', String),
        Column('description', String)
    )
    name: str
    description: str
    options: list

    __mapper_args__ = {
        'properties': {
            'options': relationship('Testoption', secondary=MappingTestfunctionToTestoption.__table__, backref='testfunctions')
        }
    }


@mapper_registry.mapped
@define(slots=False)
class Testresult:
    __table__ = Table(
        'testresult',
        mapper_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('status', String),
    )
    status: str


@mapper_registry.mapped
@define(slots=False)
class Testoption:
    __table__ = Table(
        'testoption',
        mapper_registry.metadata,
        Column('id', Integer, primary_key=True),
        Column('name', String, unique=True),
    )
    name: str

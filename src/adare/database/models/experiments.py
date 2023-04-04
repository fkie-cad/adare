from sqlalchemy import Column, Integer, String, ForeignKey, Table, DateTime
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Status(Base):
    """
        Collection of possible status.
    """
    __tablename__ = 'status'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Status(name='{self.name}')>"

class Result(Base):
    """
        Result of a test.
    """
    __tablename__ = 'result'
    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(Integer, ForeignKey('status.id'))
    details = Column(String)

    def __str__(self):
        return str(self.status)

    def __repr__(self):
        return f"<Result(status='{self.status}',details='{self.details}')>"


class TestParameter(Base):
    __tablename__ = 'testparameter'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    dtype = Column(String)


    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<TestParameter(name='{self.name}',dtype='{self.dtype}')>"


class TestParameterEntry(Base):
    __tablename__ = 'testparameterentry'
    id = Column(Integer, primary_key=True, autoincrement=True)
    parameter_id = Column(Integer, ForeignKey('testparameter.id', ondelete='CASCADE'), nullable=False)
    parameter = relationship(TestParameter)
    value = Column(String)

    def __str__(self):
        return str(self.parameter)

    def __repr__(self):
        return f"<TestParameterEntries(parameter='{self.parameter}',dtype='{self.value}')>"



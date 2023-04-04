from sqlalchemy import Column, Integer, String, ForeignKey, Table, DateTime
from sqlalchemy.orm import relationship, backref
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Status(Base):
    """
        Status of a test or experiment.
    """
    __tablename__ = 'status'
    id = Column(Integer, primary_key=True)
    name = Column(String)

    def __str__(self):
        return str(self.name)

    def __repr__(self):
        return f"<Status(name='{self.name}')>"

class Result(Base):
    __tablename__ = 'result'
    id = Column(Integer, primary_key=True)
    status = Column(Integer, ForeignKey('status.id'))
    details = Column(String)

    def __str__(self):
        return str(self.status)

    def __repr__(self):
        return f"<Result(status='{self.status}',details='{self.details}')>"
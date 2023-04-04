import sqlalchemy
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from adare.database.models.login import UserSession, Base as LoginBase
from adare.database.models.experiments import TestParameter, TestParameterEntry, Base as ExperimentsBase

class ProgramDatabase:
    def __init__(self, filename):
        self.engine = sqlalchemy.create_engine('sqlite:///' + filename)
        self.conn = self.engine.connect()
        self.metadata = sqlalchemy.MetaData()
        self.session_starter = sessionmaker()
        self.session_starter.configure(bind=self.engine)
        LoginBase.metadata.create_all(self.engine)
        ExperimentsBase.metadata.create_all(self.engine)

    def add_user_session(self, username: str, token: str, expirationdate: datetime):
        with self.session_starter.begin() as session:
            session.add(UserSession(username=username, token=token, expirationdate=expirationdate))
            session.commit()

    def add_testparameter(self, name, dtype):
        with self.session_starter.begin() as session:
            testparameter = TestParameter(name=name, dtype=dtype)
            session.add(testparameter)
            session.commit()
        return testparameter

    def add_testparameterentry(self, parameter, value):
        with self.session_starter.begin() as session:
            testparameterentry = TestParameterEntry(parameter=parameter, value=value)
            session.add(testparameterentry)
            session.commit()
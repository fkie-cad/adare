import sqlalchemy
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from adare.database.models.login import UserSession, Base as LoginBase

class ProgramDatabase:
    def __init__(self, filename):
        self.engine = sqlalchemy.create_engine('sqlite:///' + filename)
        self.conn = self.engine.connect()
        self.metadata = sqlalchemy.MetaData()
        self.session_starter = sessionmaker()
        self.session_starter.configure(bind=self.engine)
        LoginBase.metadata.create_all(self.engine)

    def add_user_session(self, username: str, token: str, expirationdate: datetime):
        with self.session_starter.begin() as session:
            session.add(UserSession(username=username, token=token, expirationdate=expirationdate))
            session.commit()

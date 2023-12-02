# external imports
from datetime import datetime
from pathlib import Path

# internal imports
import adare.config.database as config_database
from adare.database.models.login import UserSession
from adare.database.api.database import DatabaseApi
from adare.database.models.login import Base as BaseLogin

# configure logging
import logging
log = logging.getLogger(__name__)


class UserSessionApi(DatabaseApi):

    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)
        BaseLogin.metadata.create_all(self.engine)


    def __enter__(self):
        super().__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        super().__exit__(exc_type, exc_val, exc_tb)

    def add_user_session(self, username: str, token: str, expiration_date: datetime):
        self._session.add(UserSession(username=username, token=token, expirationdate=expiration_date))
        self._session.commit()
        log.debug(f'added user session for user {username} (expiration date {expiration_date})')

    def remove_user_session(self, username: str):
        user_session = self._session.query(UserSession).filter_by(username=username).first()
        if user_session:
            self._session.delete(user_session)
            self._session.commit()
            log.debug(f'removed user session for user {username}')

    def remove_expired_user_sessions(self):
        for user_session in self._session.query(UserSession).all():
            if user_session.expirationdate < datetime.now():
                self._session.delete(user_session)
                log.info(f'deleted user session for user {user_session.username}, because it expired')
        self._session.commit()

    def get_user_session(self, username: str):
        return self._session.query(UserSession).filter_by(username=username).first()

    def get_first_user_session(self):
        return self._session.query(UserSession).first()

    def check_user_session(self):
        for user_session in self._session.query(UserSession).all():
            if user_session.expirationdate < datetime.now():
                self._session.delete(user_session)
                log.info(f'deleted user session for user {user_session.username}, because it expired')
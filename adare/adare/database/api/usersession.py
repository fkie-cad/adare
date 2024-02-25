# external imports
from datetime import datetime
from pathlib import Path

# internal imports
import adare.config.database as config_database
from adare.database.models.login import UserSession, Token
from adare.database.api.database import DatabaseApi
from adare.database.models.login import Base as BaseLogin
from adare.database.exceptions import TokenExpired

# configure logging
import logging

log = logging.getLogger(__name__)


class UserSessionApi(DatabaseApi):

    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)
        BaseLogin.metadata.create_all(self.engine)

    def add_user_session(self, username: str, gitea_token: str, gitea_token_expiration: datetime, gitea_refresh_token: str, django_token: str, django_token_expiration: datetime):
        if self.get_user_session(username):
            self.remove_user_session(username)

        gitea = Token(token=gitea_token, expiration=gitea_token_expiration)
        django = Token(token=django_token, expiration=django_token_expiration)
        self._session.add(gitea)
        self._session.add(django)
        if gitea_refresh_token:
            gitea_refresh = Token(token=gitea_refresh_token)
            self._session.add(gitea_refresh)
            self._session.add(UserSession(username=username, gitea_token=gitea, django_token=django, gitea_refresh_token=gitea_refresh))
        else:
            self._session.add(UserSession(username=username, gitea_token=gitea, django_token=django))
        self._session.commit()
        log.debug(f'added user session for user {username}')

    def remove_user_session(self, username: str):
        if (
            user_session := self._session.query(UserSession)
            .filter_by(username=username)
            .first()
        ):
            if user_session.gitea_token:
                self._session.delete(user_session.gitea_token)
            if user_session.django_token:
                self._session.delete(user_session.django_token)
            if user_session.gitea_refresh_token:
                self._session.delete(user_session.gitea_refresh_token)
            self._session.delete(user_session)
            self._session.commit()
            log.debug(f'removed user session for user {username}')

    def remove_expired_user_sessions(self):
        for user_session in self._session.query(UserSession).all():
            if user_session.gitea_token.expiration < datetime.now():
                self.remove_user_session(user_session.username)
                log.info(f'deleted gitea token for user session ({user_session.username}), because it expired')
            if user_session.django_token.expiration < datetime.now():
                self.remove_user_session(user_session.username)
                log.info(f'deleted django token for user session ({user_session.username}), because it expired')
        self._session.commit()

    def get_user_session(self, username: str):
        self.remove_expired_user_sessions()
        user_session = self._session.query(UserSession).filter_by(username=username).first()
        if not user_session:
            return None
        if not user_session.gitea_token or not user_session.django_token:
            raise TokenExpired(log, f'gitea or django token for user {username} expired')
        return user_session

    def get_first_user_session(self):
        self.remove_expired_user_sessions()
        user_session = self._session.query(UserSession).first()
        if not user_session:
            return None
        if not user_session.gitea_token or not user_session.django_token:
            raise TokenExpired(log, f'gitea or django token for user {user_session.username} expired')
        return user_session


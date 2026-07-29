# external imports
# configure logging
import logging
from datetime import UTC, datetime
from pathlib import Path

# internal imports
import adare.config.database as config_database
from adare.database.api.database import DatabaseApi
from adare.database.exceptions import TokenExpired
from adare.database.models.login import Base as BaseLogin
from adare.database.models.login import Token, UserSession

log = logging.getLogger(__name__)


class UserSessionApi(DatabaseApi):
    """Database API for managing authenticated user sessions and their tokens."""

    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)
        BaseLogin.metadata.create_all(self.engine)

    def add_user_session(self, username: str, gitea_token: str, gitea_token_expiration: datetime, gitea_refresh_token: str, django_token: str, django_token_expiration: datetime):
        """Create a new user session, replacing any existing session for the user."""
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
        """Remove a user session and its associated tokens."""
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
        """Remove all user sessions whose Gitea or Django tokens have expired."""
        for user_session in self._session.query(UserSession).all():
            gitea_token_expiration = user_session.gitea_token.expiration.replace(tzinfo=UTC)
            if gitea_token_expiration <= datetime.now(UTC):
                self.remove_user_session(user_session.username)
                log.info(f'deleted gitea token for user session ({user_session.username}), because it expired')
            django_token_expiration = user_session.django_token.expiration.replace(tzinfo=UTC)
            if django_token_expiration < datetime.now(UTC):
                self.remove_user_session(user_session.username)
                log.info(f'deleted django token for user session ({user_session.username}), because it expired')
        self._session.commit()

    def get_session_for_refresh(self, username: str = None):
        """Get a user session WITHOUT pruning expired ones.

        Used by the token-refresh path, which must inspect a (possibly expired) session
        and renew its tokens before the time-based pruning would otherwise delete it.
        """
        query = self._session.query(UserSession)
        if username:
            query = query.filter_by(username=username)
        return query.first()

    def update_session_tokens(self, username: str, gitea_token: str, gitea_token_expiration: datetime, gitea_refresh_token: str, django_token: str, django_token_expiration: datetime):
        """Update the tokens of an existing session in place (used after a token refresh).

        Advancing the stored expirations here means the subsequent time-based pruning no
        longer fires for this session. Does nothing if the session no longer exists.
        """
        user_session = self._session.query(UserSession).filter_by(username=username).first()
        if not user_session:
            return
        user_session.gitea_token.token = gitea_token
        user_session.gitea_token.expiration = gitea_token_expiration
        user_session.django_token.token = django_token
        user_session.django_token.expiration = django_token_expiration
        if user_session.gitea_refresh_token:
            user_session.gitea_refresh_token.token = gitea_refresh_token
        elif gitea_refresh_token:
            refresh = Token(token=gitea_refresh_token)
            self._session.add(refresh)
            user_session.gitea_refresh_token = refresh
        self._session.commit()
        log.info(f'refreshed tokens for user session ({username})')

    def get_user_session(self, username: str):
        """Get an active user session by username after pruning expired sessions.

        Raises:
            TokenExpired: If the session exists but a required token is missing.
        """
        self.remove_expired_user_sessions()
        user_session = self._session.query(UserSession).filter_by(username=username).first()
        if not user_session:
            return None
        if not user_session.gitea_token or not user_session.django_token:
            raise TokenExpired(log, f'gitea or django token for user {username} expired')
        return user_session

    def get_first_user_session(self):
        """Get the first available active user session after pruning expired sessions.

        Raises:
            TokenExpired: If the session exists but a required token is missing.
        """
        self.remove_expired_user_sessions()
        user_session = self._session.query(UserSession).first()
        if not user_session:
            return None
        if not user_session.gitea_token or not user_session.django_token:
            raise TokenExpired(log, f'gitea or django token for user {user_session.username} expired')
        return user_session


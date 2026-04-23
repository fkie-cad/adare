# external imports
# configure logging
import logging
from pathlib import Path

import sqlalchemy
from sqlalchemy.orm import sessionmaker

# internal imports
import adare.config.database as config_database

log = logging.getLogger(__name__)


class DatabaseApi:
    """Legacy database API providing basic SQLAlchemy session management.

    This class handles database connection setup, session lifecycle,
    and common operations like add/commit and expunge.
    """

    engine: sqlalchemy.engine.base.Engine
    _session: sqlalchemy.orm.Session

    def __init__(self, db_path: Path = config_database.get_database_location()):
        self.engine = sqlalchemy.create_engine(f'sqlite:///{db_path.as_posix()}')
        self.conn = self.engine.connect()
        self.metadata = sqlalchemy.MetaData()
        self.session_starter = sessionmaker(autoflush=False, expire_on_commit=False)
        self.session_starter.configure(bind=self.engine)

    def __enter__(self):
        self.__start_sqlalchemy_session()
        if not self._session:
            log.error('Could not start sqlalchemy session.')
            return None
        # log.debug('Started sqlalchemy session.')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._session.rollback()
        else:
            self._session.commit()
        self._session.close()

    def expunge(self, obj):
        """Remove an object from the current session."""
        self._session.expunge(obj)

    def __start_sqlalchemy_session(self):
        self._session = self.session_starter()
        self._session.begin()

    def _add_commit(self, obj):
        self._session.add(obj)
        self._session.commit()
        return obj

    def _delete_commit(self, obj):
        self._session.delete(obj)
        self._session.commit()
        return obj

    def _expunge_multiple(self, objs):
        for obj in objs:
            self._session.expunge(obj)
        return objs

    def _expunge_all(self):
        self._session.expunge_all()

    def get_or_create(self, model, defaults=None, **kwargs):
        """Get an existing entity or create a new one.

        Args:
            model: SQLAlchemy model class.
            defaults: Default values merged into kwargs when creating.
            **kwargs: Filter criteria used for lookup and creation.

        Returns:
            Tuple of (instance, created) where created is True if a new
            entity was created.
        """
        if instance := self._session.query(model).filter_by(**kwargs).first():
            return instance, False
        params = {k: v for k, v in kwargs.items() if not callable(v)}
        params |= (defaults or {})
        instance = model(**params)
        self._session.add(instance)
        return instance, True

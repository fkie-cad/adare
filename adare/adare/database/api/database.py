# external imports
import sqlalchemy
from sqlalchemy.orm import sessionmaker
from pathlib import Path

# internal imports
import adare.config.database as config_database

# configure logging
import logging

log = logging.getLogger(__name__)


class DatabaseApi:
    _session: sqlalchemy.orm.Session

    def __init__(self, db_path: Path = config_database.get_database_location()):
        self.engine = sqlalchemy.create_engine(f'sqlite:///{db_path.as_posix()}')
        self.conn = self.engine.connect()
        self.metadata = sqlalchemy.MetaData()
        self.session_starter = sessionmaker(autoflush=False)
        self.session_starter.configure(bind=self.engine)

    def __enter__(self):
        self.__start_sqlalchemy_session()
        if not self._session:
            log.error('Could not start sqlalchemy session.')
            return None
        log.info('Started sqlalchemy session.')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            self.__stop_sqlalchemy_session()
            log.info('Stopped sqlalchemy session.')
        else:
            log.error('Could not stop sqlalchemy session, because session was not created.')

    def expunge(self, obj):
        self._session.expunge(obj)

    def __start_sqlalchemy_session(self):
        self._session = self.session_starter()
        self._session.begin()

    def __stop_sqlalchemy_session(self):
        self._session.commit()
        self._session.close()

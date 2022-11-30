# external imports
from pathlib import Path
import platform
import sqlalchemy
from sqlalchemy.engine import Engine

# internal imports
from adare.backend.exceptions import DatabaseWrongSuffix, PlatformNotSupported
from adare.databaseORM.experimentresults import mapper_registry

# configure logging
import logging
log = logging.getLogger(__name__)


class SqliteResultParser:
    db_path: Path
    engine: Engine

    def __init__(self, database_path: Path):
        if not database_path.suffix == '.db':
            raise DatabaseWrongSuffix(database_path.suffix)
        self.db_path = database_path
        if not database_path.is_file():
            log.info(f'database with path {database_path} is not already existing and will be created')
            local_platform = platform.system()
            if local_platform in ['Linux', 'Darwin']:
                db_uri = f'sqlite:///{database_path.absolute().as_posix()}'
            elif local_platform == 'Windows':
                db_path_windows_style = database_path.absolute().as_posix().replace('/', '\\')
                db_uri = f'sqlite:///{db_path_windows_style}'
            else:
                raise PlatformNotSupported(local_platform)
            self.engine = sqlalchemy.create_engine(db_uri)
            mapper_registry.metadata.create_all(self.engine)

    # def add_experiment(self, resultfile: Path):
    #     results = yaml_to_dict(resultfile)


if __name__ == '__main__':
    SqliteResultParser(Path(r'D:\test.db'))

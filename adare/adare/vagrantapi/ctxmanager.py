# external imports
from abc import ABC, abstractmethod

# configure logging
import logging
log = logging.getLogger(__name__)


class VagrantCtxManager(ABC):
    @abstractmethod
    def __enter__(self):
        pass

    @abstractmethod
    def set_status(self, status: str):
        pass

    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

from enum import IntEnum

# timestamp format
TIMESTAMP_FORMAT = '%Y-%m-%dT%H:%M:%S.%f'

class StatusEnum(IntEnum):
    NONE = 1
    SUCCESS = 2
    FAILED = 3
    WARNING = 4
    ERROR = 5
    RUNNING = 6
    PENDING = 7
    INTERRUPTED = 8
    FINISHED = 9
    TEST_MISSING = 12
    TEST_FAILED = 13
    PAUSE = 14

    @staticmethod
    def from_string(status_string: str):
        status_string = status_string.strip().lower()
        if status_string == 'success':
            return StatusEnum.SUCCESS
        elif status_string == 'failed':
            return StatusEnum.FAILED
        elif status_string == 'warning':
            return StatusEnum.WARNING
        elif status_string == 'error':
            return StatusEnum.ERROR
        elif status_string == 'running':
            return StatusEnum.RUNNING
        elif status_string == 'pending':
            return StatusEnum.PENDING
        elif status_string == 'interrupted':
            return StatusEnum.INTERRUPTED
        elif status_string == 'finished':
            return StatusEnum.FINISHED
        elif status_string == 'test_missing':
            return StatusEnum.TEST_MISSING
        elif status_string == 'test_failed':
            return StatusEnum.TEST_FAILED
        return StatusEnum.NONE

    @staticmethod
    def get_icon(value: int, color=False):
        colorname = StatusEnum.get_color(value) if color else ''
        icon = ''
        if value == StatusEnum.SUCCESS:
            icon = ':heavy_check_mark:'
        elif value == StatusEnum.WARNING:
            icon = ':warning:'
        elif value == StatusEnum.FAILED:
            icon = ':heavy_multiplication_x:'
        elif value == StatusEnum.ERROR:
            icon = ':x:'
        elif value == StatusEnum.FINISHED:
            icon = ':black_small_square:'
        elif value == StatusEnum.INTERRUPTED:
            icon = ':high_voltage:'
        elif value == StatusEnum.RUNNING:
            icon = ':arrow_forward:'
        elif value == StatusEnum.PENDING:
            icon = ':hourglass:'
        elif value == StatusEnum.TEST_MISSING:
            icon = ':black_medium_square:'
        elif value == StatusEnum.TEST_FAILED:
            icon = ':no_entry_sign:'
        elif value == StatusEnum.PAUSE:
            icon = ':pause_button:'
        from rich.text import Text
        return f'[{colorname}]{Text.from_markup(icon)}[/{colorname}]' if colorname else Text.from_markup(icon)

    @staticmethod
    def get_color(value: int):
        if value == StatusEnum.SUCCESS:
            return 'green'
        elif value == StatusEnum.WARNING:
            return 'yellow'
        elif value == StatusEnum.FAILED:
            return 'red'
        elif value == StatusEnum.ERROR:
            return 'red'
        elif value == StatusEnum.FINISHED:
            return 'green'
        elif value == StatusEnum.INTERRUPTED:
            return 'yellow'
        elif value == StatusEnum.RUNNING:
            return 'blue'
        elif value == StatusEnum.PENDING:
            return 'yellow'
        elif value == StatusEnum.TEST_MISSING:
            return 'blue'
        elif value == StatusEnum.TEST_FAILED:
            return 'red'
        elif value == StatusEnum.PAUSE:
            return 'yellow'
        return ''


class VMStatus(IntEnum):
    """Status values for VM availability and readiness"""
    IMPORTED = 1      # VM imported but not verified
    READY = 2         # VM exists and base snapshot available
    MISSING = 3       # VM should exist but not found in VirtualBox
    SNAPSHOT_MISSING = 4  # VM exists but base snapshot missing
    CORRUPTED = 5     # VM or snapshot corrupted/invalid


class VmInstanceStatus(IntEnum):
    """
    Lifecycle status for VM instances.

    Uses integer values with string conversion methods for database compatibility.
    """
    ACTIVE = 1          # Instance is currently in use by an experiment
    AVAILABLE = 2       # Instance is ready for reuse
    CLEANUP_PENDING = 3 # Instance is marked for cleanup

    @property
    def string_value(self) -> str:
        """Return string representation for database storage."""
        return self.name.lower()

    def __str__(self) -> str:
        """Return string representation."""
        return self.name.lower()

    @classmethod
    def from_string(cls, value: str) -> 'VmInstanceStatus':
        """Convert string value to enum."""
        value = value.strip().lower()
        mapping = {
            'active': cls.ACTIVE,
            'available': cls.AVAILABLE,
            'cleanup_pending': cls.CLEANUP_PENDING,
        }
        if value not in mapping:
            raise ValueError(f"Invalid VmInstanceStatus: {value}")
        return mapping[value]
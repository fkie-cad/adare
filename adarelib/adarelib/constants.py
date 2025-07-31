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
    BREAKPOINT_HIT = 10
    BREAKPOINT_RESOLVED = 11
    TEST_MISSING = 12
    TEST_FAILED = 13

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
        elif status_string == 'breakpoint_hit':
            return StatusEnum.BREAKPOINT_HIT
        elif status_string == 'breakpoint_resolved':
            return StatusEnum.BREAKPOINT_RESOLVED
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
        elif value == StatusEnum.BREAKPOINT_HIT:
            icon = ':stop_sign:'
        elif value == StatusEnum.BREAKPOINT_RESOLVED:
            icon = ':checkered_flag:'
        elif value == StatusEnum.TEST_MISSING:
            icon = ':question:'
        elif value == StatusEnum.TEST_FAILED:
            icon = ':no_entry_sign:'
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
        elif value == StatusEnum.BREAKPOINT_HIT:
            return 'red'
        elif value == StatusEnum.BREAKPOINT_RESOLVED:
            return 'green'
        elif value == StatusEnum.TEST_MISSING:
            return 'blue'
        elif value == StatusEnum.TEST_FAILED:
            return 'red'
        return ''
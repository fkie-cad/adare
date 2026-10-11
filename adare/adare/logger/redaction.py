"""Keep registered secrets (e.g. the per-run agent token) out of every log record."""

import logging
import threading

REDACTED = '***'

_secrets: set[str] = set()
_lock = threading.Lock()
_installed = False


def register_secret(value: str) -> None:
    """Replace ``value`` with ``***`` in all log messages from now on (process-wide)."""
    global _installed
    if not (isinstance(value, str) and value):
        return
    with _lock:
        _secrets.add(value)
        if _installed:
            return
        base_factory = logging.getLogRecordFactory()

        def factory(*args, **kwargs):
            record = base_factory(*args, **kwargs)
            if _secrets:
                message = record.getMessage()
                redacted = message
                for secret in tuple(_secrets):
                    redacted = redacted.replace(secret, REDACTED)
                if redacted != message:
                    record.msg, record.args = redacted, None
            return record

        logging.setLogRecordFactory(factory)
        _installed = True

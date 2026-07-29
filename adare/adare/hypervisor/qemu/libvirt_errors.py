"""Process-wide libvirt error handler that routes errors to Python logging.

Libvirt's C library prints error messages directly to stderr by default,
bypassing Python's logging system. Those raw lines (e.g.
``libvirt: QEMU Driver error : Cannot undefine domain with NVRAM``) leak to the
console and can corrupt the live flow-console UI. The per-call fd-level
redirect in :mod:`libvirt_stderr_redirect` cannot close all timing/thread gaps
because libvirt reports some errors from its own event loop.

Registering a process-wide error callback via
``libvirt.registerErrorHandler`` is the robust fix: once registered, libvirt
stops printing to stderr by default and hands every error to our callback,
which forwards it to a ``libvirt`` logger. From there the normal ADARE logging
rules apply -- the per-run file handler captures the message, and the
flow-console console-suppression keeps it off the terminal.
"""

# configure logging
import logging
import threading

log = logging.getLogger('libvirt')

_install_lock = threading.Lock()
_installed = False


def _libvirt_error_callback(_userdata, error):
    """Forward a libvirt error tuple to Python logging.

    Args:
        _userdata: Opaque context passed to registerErrorHandler (unused).
        error: libvirt error tuple; index 2 is the message, index 3 the level.
    """
    try:
        import libvirt

        message = error[2] if error and len(error) > 2 else str(error)
        level = error[3] if error and len(error) > 3 else None

        if level == libvirt.VIR_ERR_WARNING:
            log.warning(message)
        elif level == libvirt.VIR_ERR_ERROR:
            log.error(message)
        else:
            # VIR_ERR_NONE / unknown: still record, but don't imply severity.
            log.warning(message)
    except (IndexError, TypeError, AttributeError) as e:
        # Never let error reporting itself raise back into libvirt's C code.
        log.warning(f"libvirt error (unparseable: {e}): {error!r}")


def install_libvirt_error_logger():
    """Register the process-wide libvirt error handler exactly once.

    Idempotent and thread-safe: safe to call after every ``libvirt.open(...)``.
    """
    global _installed
    if _installed:
        return

    with _install_lock:
        if _installed:
            return
        try:
            import libvirt

            libvirt.registerErrorHandler(_libvirt_error_callback, None)
            _installed = True
            log.debug("Registered process-wide libvirt error handler")
        except (ImportError, AttributeError) as e:
            log.debug(f"Could not register libvirt error handler: {e}")

"""
CLI commands for the ADARE web server.
"""

import logging

logger = logging.getLogger(__name__)


def exec_webserver_start(arguments):
    """
    Start the ADARE web server.

    Args:
        arguments: CLI arguments with port, host, and dev mode flags
    """
    try:
        import uvicorn
    except ImportError as e:
        raise RuntimeError(
            "FastAPI and uvicorn are required to run the web server.\n"
            "Install with: pip install fastapi uvicorn[standard]"
        ) from e

    from adare.webapi.main import app

    # Get options from arguments
    port = getattr(arguments, "port", 8000)
    host = getattr(arguments, "host", "127.0.0.1")
    dev_mode = getattr(arguments, "dev", False)

    logger.info(f"Starting ADARE web server at http://{host}:{port}")

    if dev_mode:
        logger.info("Running in development mode with auto-reload")

    # Start uvicorn server
    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=dev_mode,
        log_level="info" if dev_mode else "warning",
    )

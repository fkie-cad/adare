import argparse
import asyncio
import json
import logging
import os
import platform
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_RUN_DIR = Path("C:/adare/run") if platform.system() == "Windows" else Path("/adare/run")


def __setup_logging(logfile: str = None, log_level: int = logging.INFO):
    """Setup logging with defensive directory creation.

    Args:
        logfile: Path to log file (optional)
        log_level: Logging level (default: INFO)
    """
    if not logfile:
        # Fallback: create logs directory if it doesn't exist
        if platform.system() == "Windows":
            default_log_dir = Path("C:/adare/run/logs")
        else:
            default_log_dir = Path("/adare/run/logs")

        # Ensure directory exists
        default_log_dir.mkdir(parents=True, exist_ok=True)
        logfile = str(default_log_dir / 'adarevm.log')

    # Defensive: Ensure parent directory exists for provided logfile path
    log_path = Path(logfile)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        filename=logfile,
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )


def __parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='ADARE VM Agent')
    parser.add_argument('--logfile', '-l', type=str, default=None, help='Path to log file')

    # Run directory as positional argument (optional)
    # If provided, it overrides defaults and is used to look for config.json
    parser.add_argument(
        'run_dir', nargs='?', default=str(DEFAULT_RUN_DIR), help='Path to run directory containing config.json'
    )

    parser.add_argument(
        '--tools-path',
        '-t',
        action='append',
        default=[],
        dest='tools_paths',
        help='Path to add to PATH for tools (can be specified multiple times)',
    )
    parser.add_argument(
        '--data-path',
        '-d',
        action='append',
        default=[],
        dest='data_paths',
        help='Path to data directory (can be specified multiple times)',
    )
    # Support legacy positional argument for backwards compatibility
    parser.add_argument(
        'logfile_positional', nargs='?', default=None, help=argparse.SUPPRESS
    )  # Hidden, for backwards compat
    return parser.parse_args()


async def main(
    tools_paths: list[str] = None,
    data_paths: list[str] = None,
    installation_mode: str = "wheel",
    token: str | None = None,
):
    from adarevm.core.server import AdareVMServer

    server_instance = AdareVMServer(
        tools_paths=tools_paths, data_paths=data_paths, installation_mode=installation_mode, token=token
    )
    log.info("Starting AdareVM server...")
    server = await server_instance.start_server()
    log.info("AdareVM server started successfully.")

    try:
        await server.wait_closed()
    except KeyboardInterrupt:
        log.info("Shutting down server...")
        server.close()
        await server.wait_closed()
        log.info("Server shut down successfully.")


def load_config(run_dir: str) -> dict:
    """Load configuration from config.json in run directory."""
    config_path = Path(run_dir) / "config.json"
    if not config_path.exists():
        log.warning(f"Config file not found: {config_path}")
        return {}

    try:
        with open(config_path) as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Failed to load config from {config_path}: {e}")
        return {}


def _log_shared_paths(paths: list[str], file_transfer_mode: str):
    """Log how /adare was populated and what each tools/data path holds.

    Missing or empty shares are otherwise invisible in this log, which is the
    one users send when files they shared don't show up in the guest.
    """
    log.info(f"file transfer mode: {file_transfer_mode}")
    for path in paths:
        try:
            entries = len(os.listdir(path))
        except FileNotFoundError:
            log.warning(f"shared path {path}: MISSING")
            continue
        except OSError as e:
            log.warning(f"shared path {path}: not readable ({e.strerror})")
            continue
        log.info(f"shared path {path}: {entries} entries")


def run():
    args = __parse_args()

    # Load config from file
    config = load_config(args.run_dir)

    # Merge config with args (args take precedence if specified, but usually won't be)
    # Config keys: 'tools_paths', 'data_paths', 'logfile'

    loglevel_lookup = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL,
    }

    # Resolve logfile
    logfile = args.logfile or args.logfile_positional or config.get('logfile')
    log_level = config.get('log_level', 'INFO').upper()
    log_level = loglevel_lookup.get(log_level, logging.INFO)
    __setup_logging(logfile=logfile, log_level=log_level)

    # Log version information
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            adarevm_version = version('adarevm')
        except PackageNotFoundError:
            adarevm_version = 'unknown (not installed)'

        try:
            adarelib_version = version('adarelib')
        except PackageNotFoundError:
            adarelib_version = 'unknown (not installed)'

        log.info(f"adarevm version: {adarevm_version}")
        log.info(f"adarelib version: {adarelib_version}")
    except ImportError:
        log.warning("Could not retrieve package versions (importlib.metadata not available)")

    # Resolve paths
    tools_paths = args.tools_paths + config.get('tools_paths', [])
    data_paths = args.data_paths + config.get('data_paths', [])
    installation_mode = config.get('installation_mode', 'wheel')

    log.info(
        f"adarevm started with tools_paths={tools_paths}, data_paths={data_paths}, installation_mode={installation_mode}"
    )
    # Hosts older than this key don't write it
    _log_shared_paths(tools_paths + data_paths, config.get('file_transfer_mode', 'unknown'))
    try:
        asyncio.run(
            main(
                tools_paths=tools_paths,
                data_paths=data_paths,
                installation_mode=installation_mode,
                token=config.get('agent_token'),
            )
        )
    except KeyboardInterrupt:
        log.info("adarevm interrupted by user")
    except Exception as e:
        log.critical(f"adarevm crashed: {type(e).__name__}: {e}", exc_info=True)
        for handler in logging.root.handlers:
            handler.flush()
        raise


if __name__ == "__main__":
    run()

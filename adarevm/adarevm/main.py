import argparse
import asyncio
import logging
import platform
from pathlib import Path
from typing import List

import json

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
    parser.add_argument('--logfile', '-l', type=str, default=None,
                        help='Path to log file')
    
    # Run directory as positional argument (optional)
    # If provided, it overrides defaults and is used to look for config.json
    parser.add_argument('run_dir', nargs='?', default=str(DEFAULT_RUN_DIR),
                        help='Path to run directory containing config.json')
                        
    parser.add_argument('--tools-path', '-t', action='append', default=[],
                        dest='tools_paths',
                        help='Path to add to PATH for tools (can be specified multiple times)')
    parser.add_argument('--data-path', '-d', action='append', default=[],
                        dest='data_paths',
                        help='Path to data directory (can be specified multiple times)')
    # Support legacy positional argument for backwards compatibility
    parser.add_argument('logfile_positional', nargs='?', default=None,
                        help=argparse.SUPPRESS)  # Hidden, for backwards compat
    return parser.parse_args()


async def main(tools_paths: List[str] = None, data_paths: List[str] = None):
    from adarevm.core.server import AdareVMServer
    server_instance = AdareVMServer(tools_paths=tools_paths, data_paths=data_paths)
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
        return {}
    
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Failed to load config from {config_path}: {e}")
        return {}

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
        'CRITICAL': logging.CRITICAL
    }

    # Resolve logfile
    logfile = args.logfile or args.logfile_positional or config.get('logfile')
    log_level = config.get('log_level', 'INFO').upper()
    log_level = loglevel_lookup.get(log_level, logging.INFO)
    __setup_logging(logfile=logfile, log_level=log_level)
    
    # Resolve paths
    tools_paths = args.tools_paths + config.get('tools_paths', [])
    data_paths = args.data_paths + config.get('data_paths', [])

    log.info(f"adarevm started with tools_paths={tools_paths}, data_paths={data_paths}")
    asyncio.run(main(tools_paths=tools_paths, data_paths=data_paths))

if __name__ == "__main__":
    run()
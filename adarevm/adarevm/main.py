import argparse
import asyncio
import logging
import os
import platform
import sys
from pathlib import Path
from typing import List

import json

log = logging.getLogger(__name__)

DEFAULT_RUN_DIR = Path("C:/adare/run") if platform.system() == "Windows" else Path("/adare/run")

def __setup_python_paths():
    """Setup Python paths for adarelib when in VM runtime structure."""
    # Check if adarelib is in VM runtime structure
    adarelib_path = Path("/adare/vm/adarelib")
    if adarelib_path.exists() and str(adarelib_path) not in sys.path:
        sys.path.insert(0, str(adarelib_path))
        log.info(f"Added adarelib path to Python path: {adarelib_path}")


def __setup_tools_path(tools_paths: List[str]):
    """Add tools directories to system PATH."""
    if not tools_paths:
        return

    separator = ';' if platform.system() == 'Windows' else ':'
    current_path = os.environ.get('PATH', '')

    # Add each tools path to the beginning of PATH
    for path in tools_paths:
        if path and path not in current_path:
            current_path = path + separator + current_path

    os.environ['PATH'] = current_path
    log.info(f"Added tools paths to PATH: {tools_paths}")


def __setup_logging(logfile: str = None):
    if not logfile:
        if platform.system() == "Windows":
            logfile = 'C:/adare/run/logs/adarevm.log'
        else:
            logfile = '/adare/run/logs/adarevm.log'
    logging.basicConfig(
        filename=logfile,
        level=logging.INFO,
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


async def main(data_paths: List[str] = None):
    __setup_python_paths()
    from adarevm.core.server import AdareVMServer
    server_instance = AdareVMServer(data_paths=data_paths)
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
    
    # Resolve logfile
    logfile = args.logfile or args.logfile_positional or config.get('logfile')
    __setup_logging(logfile=logfile)
    
    # Resolve paths
    tools_paths = args.tools_paths + config.get('tools_paths', [])
    data_paths = args.data_paths + config.get('data_paths', [])

    __setup_tools_path(tools_paths)
    log.info(f"adarevm started with tools_paths={tools_paths}, data_paths={data_paths}")
    asyncio.run(main(data_paths=data_paths))

if __name__ == "__main__":
    run()
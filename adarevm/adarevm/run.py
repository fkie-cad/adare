# external imports
from pathlib import Path
import argparse
import sys
import asyncio

# internal imports
from adarevm.wsserver.server import get_ws_server
from adarevm.msghandler.adare_ws_protocol_handler import AdareWsProtocolHandler

# logging configuration
from adarelib.logger import logger
import logging as log


def setup_logging(commandline, logfile: Path):
    logger.setup_logger(logfile=logfile)
    log.info(f'COMMAND: {" ".join(commandline)}')


def main():
    parser = argparse.ArgumentParser(description='run an experiment')
    parser.add_argument('logfile', type=Path, help='path to the log file')
    args = parser.parse_args()

    setup_logging(sys.argv, Path(args.logfile))

    ws_server = get_ws_server(host='10.0.2.15', port=18765)
    msg_handler = AdareWsProtocolHandler()
    ws_server.set_msg_handler(msg_handler)
    try:
        log.info('Starting WebSocket server...')
        ws_server.start()
    except KeyboardInterrupt:
        pass
    log.info('Stopping WebSocket server...')
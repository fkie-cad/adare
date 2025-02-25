# internal imports
from adarevm.wsserver.server import get_ws_server
from adarevm.msghandler.adare_ws_protocol_handler import AdareWsProtocolHandler

import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])

def main():
    ws_server = get_ws_server(host='localhost', port=18765)
    msg_handler = AdareWsProtocolHandler()
    ws_server.set_msg_handler(msg_handler)
    try:
        ws_server.start()
    except KeyboardInterrupt:
        print('Shutting down WebSocket server...')
        ws_server.stop()

if __name__ == '__main__':
    main()
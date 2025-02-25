from adare.backend.wsclient.client import WebSocketClient
from adarelib.types.ws import ECHO, ECHOREPLY, WsCommand, EXEC, EXPERIMENT, DONE
import base64

import logging
# set logging to stdout
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])

def main():
    # x = WsCommand.decode(data='ECHOREPLY: Hallo')
    # print(x)
    client = WebSocketClient("ws://localhost:18765", "test")
    client.start()
    client.is_ready()

    exec_command = EXEC(
        command='ls',
        shell=True
    )
    client.send_message(exec_command.encode())
    print("Message sent")
    done = False
    while not done:
        messages = client.fetch_messages()
        if messages:
            for msg in messages:
                x  = msg.decode('utf-8')
                y = WsCommand.decode(x)
                print(y.out_msg)
                print(y.err_msg)
                done = True
                break

    # experiment_command = EXPERIMENT(
    #     name='deletefile',
    # )
    # client.send_message(experiment_command.encode())
    # print("Message sent")
    # done = False
    # while not done:
    #     messages = client.fetch_messages()
    #     if messages:
    #         for msg in messages:
    #             x  = msg.decode('utf-8')
    #             y = WsCommand.decode(x)
    #             print(y)
    #             if type(msg) == DONE:
    #                 done = True



if __name__ == '__main__':
    main()
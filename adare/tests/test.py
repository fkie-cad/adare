from adare.backend.wsclient.client import WebSocketClient
from adarelib.types.ws import ECHO, ECHOREPLY, WsCommand, EXEC, EXPERIMENT, DONE
import base64
import asyncio

import logging
# set logging to stdout
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.StreamHandler()])

async def main():
    from websockets.asyncio.client import connect

    # async def hello():
    #     async with connect("ws://localhost:18765") as websocket:
    #         exec_command = EXEC(
    #             command='ls',
    #             shell=True
    #         )
    #         await websocket.send("adare")
    #         await websocket.send(exec_command.encode())
    #         print("Message sent")
    #         done = False
    #         while not done:
    #             messages = await websocket.recv()
    #             x = messages.decode('utf-8')
    #             y = WsCommand.decode(x)
    #             print(y.out_msg)
    #             print(y.err_msg)
    #             done = True
    #
    # await hello()
    client = WebSocketClient("ws://localhost:18765", "test")
    await client.wait_until_server_ready(ping_timeout=20)

    exec_command = EXEC(
        command='ls',
        shell=True
    )
    await client.send_message(exec_command.encode())
    print("Message sent")
    while True:
        msg = await client.fetch_message()
        if msg:
            x  = msg.decode('utf-8')
            y = WsCommand.decode(x)
            print(y.out_msg)
            print(y.err_msg)
            await client.close()
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
    asyncio.run(main())
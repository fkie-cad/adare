from adare.backend.experiment.websocket_client import AdareVMClient


if __name__ == "__main__":
    import asyncio
    import logging

    logging.basicConfig(level=logging.DEBUG, handlers=[logging.StreamHandler()])

    async def main():
        client = AdareVMClient()
        result = await client.connect(timeout=5)
        print(result)
        result = await client.get_status()
        print(result)

    asyncio.run(main())

        
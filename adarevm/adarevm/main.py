import asyncio
import logging
log = logging.getLogger(__name__)



def __setup_logging():
    import platform
    if platform.system() == "Windows":
        logfile = 'C:/adare/run/adarevm.log'
    else:
        logfile = '/adare/run/adarevm.log'
    logging.basicConfig(
        filename=logfile,
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )


async def main():
    from adarevm.core.server import AdareVMServer
    server_instance = AdareVMServer()
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


if __name__ == "__main__":
    __setup_logging()
    asyncio.run(main())
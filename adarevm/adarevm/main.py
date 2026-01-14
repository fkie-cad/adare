import asyncio
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def __setup_python_paths():
    """Setup Python paths for adarelib when in VM runtime structure."""
    # Check if adarelib is in VM runtime structure
    adarelib_path = Path("/adare/vm/adarelib")
    if adarelib_path.exists() and str(adarelib_path) not in sys.path:
        sys.path.insert(0, str(adarelib_path))
        log.info(f"Added adarelib path to Python path: {adarelib_path}")



def __setup_logging(logfile: str = None):
    if not logfile:
        import platform
        if platform.system() == "Windows":
            logfile = 'C:/adare/run/logs/adarevm.log'
        else:
            logfile = '/adare/run/logs/adarevm.log'
    logging.basicConfig(
        filename=logfile,
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )

async def main():
    __setup_python_paths()
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


def run():
    import sys
    logfile = sys.argv[1] if len(sys.argv) > 1 else None
    __setup_logging(logfile=logfile)
    asyncio.run(main())

if __name__ == "__main__":
    run()
# external imports
import asyncio

# configure logging
import logging

import aiohttp

# internal imports
import adare.config.server as config_server

log = logging.getLogger(__name__)


async def check_webserver_availability():
    """
    Check if the webserver is available
    :return:
    """
    req_session = aiohttp.ClientSession()
    try:
        async with req_session.get(config_server.API_URL, timeout=config_server.TIMEOUT_SECONDS):
            pass
    except aiohttp.ClientConnectionError:
        await req_session.close()
        return False
    # deal with this type of exception
    except asyncio.exceptions.TimeoutError:
        await req_session.close()
        return False
    await req_session.close()
    return True

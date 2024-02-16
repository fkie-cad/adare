# external imports
import aiohttp
import asyncio

# internal imports
import adare.config.server as config_server
from adare.database.api.experiment import ExperimentApi

# configure logging
import logging
log = logging.getLogger(__name__)


async def check_experiment_published(experiment_uuid, force_check=False, component_func=None, post_func=None):
    """
    Check if the experiment is published to the webapp
    :param post_func:
    :param component_func:
    :param force_check: force a check even if the publish status is known
    :param experiment_uuid: the experiment uuid
    """

    with ExperimentApi() as experiment_api:
        experiment = experiment_api.get_experiment_by_uuid(experiment_uuid)
        if not experiment:
            log.error(f"Experiment with uuid {experiment_uuid} not found in database")
            raise ValueError(f"Experiment with uuid {experiment_uuid} not found in database")
        # get published status from database
        publish_status = experiment.publish_status
        if publish_status.name == "published" and not force_check:
            return
        elif publish_status.name == "not published" and not force_check:
            return
        elif publish_status.name == "unknown" or force_check:
            log.info(f"Check publish status of experiment {experiment_uuid}")
            # request publish status from webapp by sending experiment hash to api
            session = aiohttp.ClientSession()
            try:
                url = config_server.CHECK_EXPERIMENT_URL + f"?sha256hash={experiment.experiment_hash}"
                async with session.get(url, timeout=config_server.TIMEOUT_SECONDS) as response:
                    if response.status == 200:
                        response_json = await response.json()
                        if not response_json['uuid']:
                            experiment_api.set_experiment_publish_status(experiment_uuid=experiment_uuid, publish_status="not published")
                            log.info(f"Experiment {experiment_uuid} is not published")
                            if component_func:
                                component_func.refresh('not published')
                            if post_func:
                                post_func()
                        else:
                            if response_json['published']:
                                experiment_api.set_experiment_publish_status(experiment_uuid=experiment_uuid, publish_status="published")
                                log.info(f"Experiment {experiment_uuid} is published")
                                if component_func:
                                    component_func.refresh('published')
                                if post_func:
                                    post_func()
                            else:
                                experiment_api.set_experiment_publish_status(experiment_uuid=experiment_uuid, publish_status="in request")
                                log.info(f"Experiment {experiment_uuid} is contained in a non accepted request")
                                if component_func:
                                    component_func.refresh('in request')
                                if post_func:
                                    post_func()
                    else:
                        log.error(f'request error ({response.status})')
            except asyncio.exceptions.TimeoutError as e:
                log.error("request failed due to timeout")
            except aiohttp.ClientConnectorError as e:
                log.error("request failed due to connection error")
                log.error(e, exc_info=True)
            finally:
                await session.close()

        else:
            log.error(f"Unknown publish status {publish_status.name}")
            raise ValueError(f"Unknown publish status {publish_status.name}")




# external imports
import aiohttp
import asyncio
import json

# internal imports
import adare.config.server as config_server
from adare.database.api.request import RequestSessionApi
from adare.webappaccess.login import WebappLogin
from adare.webappaccess.request_header import get_authenticated_request_header

# configure logging
import logging
log = logging.getLogger(__name__)


async def check_request(request_uuid: str):
    """
    Check if the request is published to the webapp and if yes return information about the actual status of the request

    :param request_uuid: uuid of the request
    :return: dict with keys exists and status
    """

    aiohttp_session = aiohttp.ClientSession()
    try:
        async with aiohttp_session.get(config_server.CHECK_REQUEST_URL + f"?uuid={request_uuid}", timeout=config_server.TIMEOUT_SECONDS) as response:
            if response.status == 200:
                response_json = await response.json()
                return response_json
            else:
                log.error(f'request error ({response.status}, {await response.text()})')
                return None
    except asyncio.exceptions.TimeoutError as e:
        log.error("request failed due to timeout")
        return None
    except aiohttp.ClientConnectorError as e:
        log.error("request failed due to connection error")
        log.error(e, exc_info=True)
        return None


async def send_experiment_request(request_uuid: str):
    """
    send an experiment request to the webapp

    :param request_uuid: uuid of the request
    :return: (bool, str) tuple with success boolean and error message to be displayed to the user
    """
    aiohttp_session = aiohttp.ClientSession()

    with RequestSessionApi() as db:
        login_interface = WebappLogin()
        usersession = login_interface.get_user_session()
        if not usersession:
            log.error("no user is logged in")
            return False, f"no user is logged in"
        token = usersession.token

        # set token in header
        aiohttp_session.headers.update(get_authenticated_request_header(token))

        request = db.get_request_by_uuid(request_uuid)

        if not request:
            log.error(f"Request with uuid {request_uuid} not found in database")
            return False, f"Request with uuid {request_uuid} not found in database"

        # get experiment action and testset file
        experiment = request.experiment
        action_file = experiment.action_file
        testset_file = experiment.testset_file

        # get file handles
        action_file_handle = open(action_file, 'rb')
        testset_file_handle = open(testset_file, 'rb')

        data = {
            'title': request.title,
        }

        #
        experiment_data = {
            'uuid': experiment.uuid,
            'name': experiment.name,
            'description': experiment.description,
            'tags': [
                {
                    'name': tag.name,
                } for tag in experiment.tags
            ],
            'os_info': {
                'os': experiment.os_info.os,
                'distribution': experiment.os_info.distribution,
                'version': experiment.os_info.version,
                'language': experiment.os_info.language,
                'architecture': experiment.os_info.architecture,
                'details': experiment.os_info.details,
            },
            'abstract_tests': [
                {
                    'uuid': abstract_test.uuid,
                    'name': abstract_test.name,
                    'description': abstract_test.description,
                    'testfunction': {
                        'type': abstract_test.testfunction.type,
                        'name': abstract_test.testfunction.name,
                        'description': abstract_test.testfunction.description,
                        'possible_parameters': [
                            {
                                'name': parameter.name,
                                'dtype': parameter.dtype,
                            } for parameter in abstract_test.testfunction.possible_parameters
                        ],
                    },
                    'parameters': [
                        {
                            'value': parameter.value,
                            'parameter': {
                                'name': parameter.parameter.name,
                                'dtype': parameter.parameter.dtype,
                            },
                        } for parameter in abstract_test.parameters
                    ],
                    'tool': {
                        'name': abstract_test.tool.name,
                        'command': abstract_test.tool.command,
                    } if abstract_test.tool else None,

                } for abstract_test in experiment.abstract_tests
            ],
        }
        data['experiment'] = experiment_data

        error_msg = ""

        # rewrite the data dict to multipart/form-data
        with aiohttp.MultipartWriter("form-data") as mpwriter:
            # add files as action_file and testset_file
            action_file_mp = mpwriter.append(
                action_file_handle.read(),
            )
            action_file_mp.set_content_disposition('form-data', name='action_file', filename='action_file')
            testset_file_mp = mpwriter.append(
                testset_file_handle.read(),
            )
            testset_file_mp.set_content_disposition('form-data', name='testset_file', filename='testset_file')
            # add experiment data as json
            metadata_mp = mpwriter.append(json.dumps(data))
            metadata_mp.set_content_disposition('json', name='metadata')


        try:
            async with aiohttp_session.post(config_server.ADD_EXPERIMENT_REQUEST_URL, data=mpwriter) as resp:
                if resp.status == 200:
                    log.info("sending an experiment request was successful")
                elif resp.status == 401:
                    log.error("sending an experiment request failed due to authentication error")
                    error_msg = f"authentication failed"
                elif resp.status == 400:
                    log.error("sending an experiment request failed due to bad request")
                    error_msg = f"bad request"
                else:
                    response_text = await resp.text()
                    log.error(f"request error ({resp.status}, {response_text})")
                    error_msg = f"request error ({resp.status}, {response_text})"



        except asyncio.exceptions.TimeoutError as e:
            log.error("request failed due to timeout")
            error_msg = f"server ({config_server.WEBSERVER_URL}) is not reachable (timeout)"
        except aiohttp.ClientConnectorError as e:
            log.error("request failed due to connection error")
            log.error(e, exc_info=True)
            error_msg = f"server ({config_server.WEBSERVER_URL}) is not reachable (connection error)"
        finally:
            await aiohttp_session.close()

        # close file handles
        action_file_handle.close()
        testset_file_handle.close()

        if error_msg:
            return False, error_msg
        else:
            return True, None
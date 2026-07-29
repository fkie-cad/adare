"""Tests for the local webapi environment gate, gate 2 (T12).

Gate 2 is not a trust boundary — gates 1 and 5 are — but it is what keeps the web
dialog from ever producing an unpublishable environment, so its rejections must
be precise and its error codes stable (the TypeScript dialog switches on them).
"""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

from adare.webapi.routes.environments import (
    EnvironmentCreateBody,
    _validate_url_format,
    create_environment,
)

SHA = 'a' * 64
UBUNTU_ISO = 'https://releases.ubuntu.com/24.04/ubuntu-24.04-live-server-amd64.iso'


# --- _validate_url_format ---

@pytest.mark.parametrize('url,sha,kind,vm_format,expected_ok', [
    ('https://x.example/y.qcow2', SHA, 'vm', None, True),
    ('http://x.example/y.qcow2', SHA, 'vm', None, True),
    ('https://x.example/y.iso', SHA, 'iso', None, True),
    # no disk extension -> vm_format required for a baked VM, irrelevant for an ISO
    ('https://cloud.example/s/T/download', SHA, 'vm', None, False),
    ('https://cloud.example/s/T/download', SHA, 'vm', 'qcow2', True),
    ('https://cloud.example/s/T/download', SHA, 'iso', None, True),
    # scheme / host
    ('ftp://x.example/y.qcow2', SHA, 'vm', None, False),
    ('/local/path/y.qcow2', SHA, 'vm', None, False),
    ('https:///y.qcow2', SHA, 'vm', None, False),
    # digest
    ('https://x.example/y.iso', None, 'iso', None, False),
    ('https://x.example/y.iso', '', 'iso', None, False),
    ('https://x.example/y.iso', 'a' * 63, 'iso', None, False),
    ('https://x.example/y.iso', 'a' * 65, 'iso', None, False),
    ('https://x.example/y.iso', 'z' * 64, 'iso', None, False),
    ('https://x.example/y.iso', 'A' * 64, 'iso', None, False),
    # vm_format allow-list
    ('https://x.example/y.qcow2', SHA, 'vm', 'iso', False),
])
def test_validate_url_format(url, sha, kind, vm_format, expected_ok):
    reason = _validate_url_format(url, sha, kind, vm_format)
    assert (reason is None) is expected_ok, reason


# --- create_environment gate ---

def _body(**overrides) -> EnvironmentCreateBody:
    defaults = dict(project_path='/tmp/project', name='env1')
    defaults.update(overrides)
    return EnvironmentCreateBody(**defaults)


async def _create(body):
    """Call the async route with the service layer stubbed out.

    The gate must reject before the service is reached, so a call that gets
    through is itself a signal.
    """
    api = MagicMock()
    api.environment.create.return_value = MagicMock(
        success=True, data=None, warnings=None, error=None,
    )
    with (
        patch('adare.webapi.routes.environments._api', return_value=api),
        patch('adare.webapi.routes.environments.result_to_response',
              side_effect=lambda r: {'success': True}),
    ):
        response = await create_environment(body)
    return response, api


@pytest.mark.asyncio
async def test_byo_iso_with_a_linux_profile_is_rejected():
    response, api = await _create(_body(
        os_profile='ubuntu2404', iso_name='ubuntu-24.04-live-server-amd64.iso',
        iso_sha256=SHA,
    ))
    assert response['success'] is False
    assert response['error']['code'] == 'ByoIsoRequiresWindowsProfile'
    api.environment.create.assert_not_called()


@pytest.mark.asyncio
async def test_byo_iso_rejection_names_the_url_to_host_instead():
    response, _ = await _create(_body(
        os_profile='ubuntu2404', iso_name='ubuntu.iso', iso_sha256=SHA,
    ))
    assert 'releases.ubuntu.com' in ' '.join(response['error']['solutions'])


@pytest.mark.asyncio
async def test_byo_iso_with_a_windows_profile_reaches_the_service():
    response, api = await _create(_body(
        os_profile='windows11arm64', iso_name='Win11_25H2_English_Arm64_v2.iso',
        iso_sha256=SHA, iso_notes='From Microsoft',
    ))
    assert response == {'success': True}
    api.environment.create.assert_called_once()
    dto = api.environment.create.call_args.args[0]
    assert dto.iso_name == 'Win11_25H2_English_Arm64_v2.iso'
    assert dto.iso_notes == 'From Microsoft'


@pytest.mark.asyncio
async def test_both_iso_url_and_iso_name_is_rejected():
    response, api = await _create(_body(
        os_profile='windows11arm64', iso_url='https://x.example/w.iso',
        iso_name='w.iso', iso_sha256=SHA,
    ))
    assert response['error']['code'] == 'AmbiguousIsoSource'
    api.environment.create.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_profile_with_byo_is_rejected():
    response, _ = await _create(_body(
        os_profile='windows12quantum', iso_name='w.iso', iso_sha256=SHA,
    ))
    assert response['error']['code'] == 'UnknownOsProfileError'


@pytest.mark.asyncio
async def test_iso_name_without_an_os_profile_is_rejected():
    response, _ = await _create(_body(iso_name='w.iso', iso_sha256=SHA))
    assert response['error']['code'] == 'MissingOsProfile'


@pytest.mark.asyncio
@pytest.mark.parametrize('bad_name', [
    '../../etc/passwd', '/abs/Win11.iso', 'sub/dir/w.iso', 'C:\\ISO\\Win11.iso',
    'https://x.example/w.iso', 'Win11.img', 'x' * 250 + '.iso',
])
async def test_bad_iso_name_is_rejected(bad_name):
    response, api = await _create(_body(
        os_profile='windows11arm64', iso_name=bad_name, iso_sha256=SHA,
    ))
    assert response['error']['code'] == 'InvalidIsoName'
    api.environment.create.assert_not_called()


@pytest.mark.asyncio
async def test_a_malformed_recipe_iso_url_is_now_rejected():
    """Previously unchecked: only `vm_url` was format-validated here."""
    response, api = await _create(_body(
        os_profile='ubuntu2404', iso_url='/isos/ubuntu.iso', iso_sha256=SHA,
    ))
    assert response['error']['code'] == 'InvalidIsoUrl'
    api.environment.create.assert_not_called()


@pytest.mark.asyncio
async def test_a_recipe_iso_url_without_a_sha_is_rejected():
    response, _ = await _create(_body(os_profile='ubuntu2404', iso_url=UBUNTU_ISO))
    assert response['error']['code'] == 'InvalidIsoUrl'


@pytest.mark.asyncio
async def test_an_uppercase_recipe_iso_sha_is_rejected():
    """Canonical form only: the server stores it verbatim for other clients."""
    response, _ = await _create(_body(
        os_profile='ubuntu2404', iso_url=UBUNTU_ISO, iso_sha256='A' * 64,
    ))
    assert response['error']['code'] == 'InvalidIsoUrl'


@pytest.mark.asyncio
async def test_a_valid_recipe_url_create_reaches_the_service():
    response, api = await _create(_body(
        os_profile='ubuntu2404', iso_url=UBUNTU_ISO, iso_sha256=SHA, setup_level=1,
    ))
    assert response == {'success': True}
    api.environment.create.assert_called_once()


@pytest.mark.asyncio
async def test_a_baked_url_create_still_works():
    response, api = await _create(_body(
        vm_url='https://x.example/disk.qcow2', vm_sha256=SHA, vm_format='qcow2',
    ))
    assert response == {'success': True}
    api.environment.create.assert_called_once()


@pytest.mark.asyncio
async def test_a_baked_local_path_is_still_rejected():
    response, api = await _create(_body(vm_url='/local/disk.qcow2', vm_sha256=SHA))
    assert response['error']['code'] == 'InvalidVmUrl'
    api.environment.create.assert_not_called()

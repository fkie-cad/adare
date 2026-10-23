"""An environment file without `hypervisor:` gets one inferred from its disk."""

import pytest

from adare.types.environment import EnvironmentMetadata

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ('fields', 'expected'),
    [
        ({'vm': '/disks/ubuntu.qcow2'}, 'qemu'),
        ({'vm': '/disks/win10.ova'}, 'virtualbox'),
        ({'vm': 'https://example.org/files/win10.OVA/content'}, 'qemu'),  # no recognized suffix
        ({'vm': 'https://example.org/s/TOKEN/download', 'vm_format': 'ova'}, 'virtualbox'),
        ({'vm': 'https://example.org/disk.vmdk?dl=1'}, 'virtualbox'),
        ({'vm': '/disks/ubuntu.qcow2', 'hypervisor': 'virtualbox'}, 'virtualbox'),  # explicit wins
    ],
)
def test_hypervisor_is_inferred_from_the_disk(fields, expected):
    assert EnvironmentMetadata(**fields).hypervisor == expected

"""Every built-in testfunction's parameters can be structured the way a real run does it.

Testfunction unit tests build parameter objects directly, which skips cattrs. A run structures
the playbook's ``parameter:`` block with ``cattrs.structure`` plus the primitive-union hook, and
a type cattrs has no hook for (e.g. ``str | int | list``) makes every test using that function
fail to load. This test catches such types before a playbook does.
"""

from pathlib import Path

import attrs
import cattrs
import pytest
from cattrs.errors import StructureHandlerNotFoundError

from adare.backend.experiment.test_loader import is_plain_union, register_primitive_union_hook
from adarelib.helper.module import import_module_from_pyfile

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[4] / 'appdata' / 'testfunctions'

# Known to fail on structuring (existing debt, not to be extended): fix the type, then remove it here.
KNOWN_UNSTRUCTURABLE: set[str] = set()

_SAMPLES = ('text', 1, 1.5, True, None, ['a', 'b'], {'a': 1})


def _fields():
    for path in sorted(COLLECTIONS.glob('*/*.py')):
        module = import_module_from_pyfile(path)
        for name, obj in vars(module).items():
            parameter_class = getattr(obj, '_parameter_class', None)
            if parameter_class is None:
                continue
            for field in attrs.fields(parameter_class):
                yield pytest.param(field.type, id=f'{path.parent.name}.{name}.{field.name}')


@pytest.mark.parametrize('field_type', list(_fields()))
def test_parameter_type_can_be_structured(field_type, request):
    register_primitive_union_hook()
    field_id = request.node.callspec.id
    missing_hook = False
    for sample in _SAMPLES:
        try:
            cattrs.structure(sample, field_type)
        except StructureHandlerNotFoundError:
            missing_hook = True
            break
        except (ValueError, TypeError, AttributeError, cattrs.errors.BaseValidationError):
            continue  # a wrong value for this type is fine; only a missing hook matters
    if field_id in KNOWN_UNSTRUCTURABLE:
        assert missing_hook, f'{field_id} structures now: remove it from KNOWN_UNSTRUCTURABLE'
    else:
        assert not missing_hook, f'cattrs cannot structure {field_id}: {field_type}'


@pytest.mark.parametrize(
    ('field_type', 'value'),
    [
        (str | int | float, 1.5),
        (int | dict[str, int] | None, {'min': 1, 'max': 5}),
        (int | dict[str, int] | None, 3),
        (str | int | float | bool | dict | list, [{'a': 1}]),
        (str | int | bytes, b'\x00'),
        (list[str] | str | None, 'utf-8'),
        (list[str] | str | None, ['utf-8', 1]),  # not converted: the testfunction validates it
    ],
)
def test_plain_unions_pass_the_value_through(field_type, value):
    register_primitive_union_hook()

    assert cattrs.structure(value, field_type) is value


@pytest.mark.parametrize(
    ('field_type', 'plain'),
    [
        (str | None, True),
        (list[str] | dict[str, list[int]], True),
        (int | Path, False),
        (str | tuple[int, int], False),
        (list[str], False),  # not a union: cattrs handles it
        (int, False),
    ],
)
def test_is_plain_union(field_type, plain):
    assert is_plain_union(field_type) is plain

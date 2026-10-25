"""Behaviour of VariableResolver: YAML tags and Jinja templates -> values or placeholders + metadata."""

import datetime

import jinja2
import pytest

from adare.backend.experiment.variable_resolver import VariableResolver
from adare.types.playbook import ActionTestAction, ClickAction, CommandAction, PullAction, Target
from adarelib.common.variables import TimestampMetadata, Variable, VariableRegistry, VariableType
from adarelib.testset.yaml.customtags import YamlRegexString, YamlTimestamp

pytestmark = pytest.mark.unit

T = 1792843200.0  # 2026-10-24 12:00:00 UTC
# How save_timestamp stores it in the registry (the execution context gets the float).
T_VAR = Variable(datetime.datetime.fromtimestamp(T, datetime.UTC), VariableType.TIMESTAMP)


def _resolver(variables: dict | None = None, with_filters: bool = False) -> VariableResolver:
    registry = VariableRegistry()
    for name, variable in (variables or {}).items():
        registry.add(name, variable)
    env = None
    if with_filters:
        env = jinja2.Environment()
        env.filters.update(TimestampMetadata().get_jinja_filters(registry))
    return VariableResolver(variable_registry=registry, jinja_env=env)


class TestYamlTags:
    def test_regex_tag_in_entry_list(self):
        resolver = _resolver()
        out = resolver.process_data({'parameter': {'entry': ['a', YamlRegexString('.*')]}}, {'x': 1})
        assert out['parameter']['entry'] == ['a', '{{ regex_0_resolved }}']
        assert resolver.get_placeholder_metadata()['regex_0_resolved'] == {
            'raw_value': '.*',
            'resolved_value': '.*',
            'type': 'regex',
        }

    def test_timestamp_with_tolerance_in_list_keeps_placeholder(self):
        resolver = _resolver()
        context = {'t': T}
        out = resolver.process_data(
            {'parameter': {'entry': [YamlTimestamp(timestamp='{{ t }}', tolerance=5, format='%Y')]}}, context
        )
        assert out['parameter']['entry'] == ['{{ t_resolved }}']
        metadata = resolver.get_placeholder_metadata()['t_resolved']
        assert metadata['type'] == 'timestamp'
        assert metadata['resolved_value'] == str(T)
        assert metadata['tolerance'] == 5
        assert metadata['format'] == '%Y'
        assert 't_resolved' not in context  # stays a placeholder for the test to compare

    def test_timestamp_without_tolerance_is_resolved(self):
        out = _resolver().process_data({'parameter': {'entry': [YamlTimestamp(timestamp='{{ t }}')]}}, {'t': T})
        assert out['parameter']['entry'] == [str(T)]

    def test_template_set_later_in_the_run_is_kept(self):
        resolver = _resolver()
        out = resolver.process_data(
            {'parameter': {'entry': [YamlTimestamp(timestamp='{{ later }}', tolerance=5)]}}, {'x': 1}
        )
        assert out['parameter']['entry'] == ['{{ later_resolved }}']
        assert resolver.get_placeholder_metadata()['later_resolved']['resolved_value'] == '{{ later }}'

    def test_single_timestamp_tag_in_mapping(self):
        resolver = _resolver()
        out = resolver.process_data(
            {'parameter': {'expected': YamlTimestamp(timestamp='{{ t }}', tolerance=2)}}, {'t': T}
        )
        placeholder = out['parameter']['expected']
        name = placeholder.strip('{} ')
        assert resolver.get_placeholder_metadata()[name]['tolerance'] == 2

    def test_plain_values_untouched(self):
        data = {'name': 'n', 'parameter': {'dst': '/tmp/x', 'n': 3, 'entry': ['a', 1]}}
        assert _resolver().process_data(data, {'x': 1}) == data


class TestJinjaTemplates:
    def test_plain_variable_in_mixed_text(self):
        out = _resolver(with_filters=True).process_data({'parameter': {'dst': '{{ out }}/utc.csv'}}, {'out': '/tmp/c'})
        assert out['parameter']['dst'] == '/tmp/c/utc.csv'

    def test_tolerance_filter_becomes_placeholder(self):
        resolver = _resolver({'t': T_VAR}, with_filters=True)
        out = resolver.process_data({'parameter': {'expected': '{{ t | tolerance(5) }}'}}, {'t': T})
        assert out['parameter']['expected'] == '{{ t_resolved }}'
        metadata = resolver.get_placeholder_metadata()['t_resolved']
        assert metadata['type'] == 'timestamp' and metadata['tolerance'] == [5, -5]

    def test_format_filter_formats_value(self):
        resolver = _resolver({'t': T_VAR}, with_filters=True)
        out = resolver.process_data({'parameter': {'day': "{{ t | format('%Y-%m-%d') }}"}}, {'t': T})
        assert out['parameter']['day'] == '2026-10-24'

    def test_own_placeholders_not_reprocessed(self):
        out = _resolver(with_filters=True).process_data({'parameter': {'v': '{{ x_resolved }}'}}, {'y': 1})
        assert out['parameter']['v'] == '{{ x_resolved }}'


class TestActionVariables:
    def test_command_fields(self):
        action = CommandAction(command='echo {{ a }}', cwd='{{ d }}', env={'K': '{{ a }}'}, description='run {{ a }}')
        resolved = _resolver().resolve_action_variables(action, {'a': 'x', 'd': '/tmp'})
        assert (resolved.command, resolved.cwd, resolved.env, resolved.description) == (
            'echo x',
            '/tmp',
            {'K': 'x'},
            'run x',
        )
        assert action.command == 'echo {{ a }}'  # the original is not modified

    def test_pull_list_and_target(self):
        resolver = _resolver()
        pull = resolver.resolve_action_variables(PullAction(src=['{{ d }}/a', '{{ d }}/b']), {'d': '/x'})
        assert pull.src == ['/x/a', '/x/b']
        click = resolver.resolve_action_variables(ClickAction(target=Target(text='{{ name }}')), {'name': 'OK'})
        assert click.target.text == 'OK'

    def test_keyboard_save_timestamp_and_drag(self):
        from adare.types.playbook import DragAction, KeyboardAction, SaveTimestampAction

        resolver = _resolver()
        context = {'w': 'hello', 'v': 't0', 'a': 'A', 'b': 'B'}
        assert resolver.resolve_action_variables(KeyboardAction(text='{{ w }}'), context).text == 'hello'
        assert resolver.resolve_action_variables(SaveTimestampAction(variable='{{ v }}'), context).variable == 't0'
        drag = resolver.resolve_action_variables(
            DragAction(src=Target(text='{{ a }}'), dst=Target(text='{{ b }}')), context
        )
        assert (drag.src.text, drag.dst.text) == ('A', 'B')

    def test_test_name(self):
        assert _resolver().resolve_action_variables(ActionTestAction(name='t_{{ n }}'), {'n': 1}).name == 't_1'

    def test_raw_string_literal(self):
        assert _resolver().replace_variables('r"C:\\{{ d }}"', {'d': 'x'}) == 'C:\\x'

    def test_nested_variables_resolve(self):
        assert _resolver().replace_variables('{{ a }}', {'a': '{{ b }}', 'b': 'end'}) == 'end'

    def test_undefined_variable_raises(self):
        with pytest.raises(jinja2.UndefinedError):
            _resolver().replace_variables('{{ missing }}', {})


class TestNestedTags:
    def test_tags_inside_mappings_in_a_list(self):
        # e.g. sqlite.query_result expected_result: [{visit_time: !timestamp ...}]
        resolver = _resolver()
        out = resolver.process_data(
            {'parameter': {'expected_result': [{'url': YamlRegexString('.*x'), 'n': 1}]}}, {'x': 1}
        )
        assert out['parameter']['expected_result'] == [{'url': '{{ regex_0_resolved }}', 'n': 1}]

    def test_tags_beside_a_tagged_entry_are_converted(self):
        resolver = _resolver()
        out = resolver.process_data(
            {'parameter': {'entry': [YamlRegexString('a')], 'header': YamlRegexString('b')}}, {'x': 1}
        )
        assert out['parameter']['entry'] == ['{{ regex_0_resolved }}']
        assert out['parameter']['header'] == '{{ regex_1_resolved }}'

    def test_same_variable_twice_gets_distinct_placeholders(self):
        resolver = _resolver()
        out = resolver.process_data(
            {
                'parameter': {
                    'entry': [
                        YamlTimestamp(timestamp='{{ t }}', tolerance=1),
                        YamlTimestamp(timestamp='{{ t }}', tolerance=60),
                    ]
                }
            },
            {'t': T},
        )
        first, second = (p.strip('{} ') for p in out['parameter']['entry'])
        assert first != second
        metadata = resolver.get_placeholder_metadata()
        assert (metadata[first]['tolerance'], metadata[second]['tolerance']) == (1, 60)

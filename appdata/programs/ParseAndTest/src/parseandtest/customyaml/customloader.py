import yaml
from .customtags import YamlRegexString, YamlRegexStringAll, YamlString, YamlTimestamp, YamlPath

# list of custom tags
YAML_CUSTOM_TAGS = [YamlRegexString, YamlRegexStringAll, YamlTimestamp, YamlString, YamlPath]


def create_custom_yaml_loader_dumper(custom_tags: list):
    class YamlCustomLoader(yaml.SafeLoader):
        pass

    class YamlCustomDumper(yaml.SafeDumper):
        pass

    for TagClass in custom_tags:
        # Required for safe_load
        YamlCustomLoader.add_constructor(TagClass.yaml_tag, TagClass.from_yaml)
        # Required for safe_dump
        YamlCustomDumper.add_multi_representer(TagClass, TagClass.to_yaml)

    return YamlCustomLoader, YamlCustomDumper


def create_yaml_loader_dumper_inputfiles():
    return create_custom_yaml_loader_dumper(YAML_CUSTOM_TAGS)

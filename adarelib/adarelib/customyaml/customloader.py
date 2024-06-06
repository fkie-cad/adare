import yaml
from .customtags import YamlRegexString, YamlRegexStringAll, YamlString, YamlTimestamp, YamlPath

from adarelib.config import StatusEnum

# list of custom tags
YAML_CUSTOM_TAGS = [YamlRegexString, YamlRegexStringAll, YamlTimestamp, YamlString, YamlPath]


def create_custom_yaml_loader_dumper_testset(custom_tags: list):
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


YAML_TESTSET_LOADER, YAML_TESTSET_DUMPER = create_custom_yaml_loader_dumper_testset(YAML_CUSTOM_TAGS)


def create_custom_yaml_loader_dumper_status_enum():
    class YamlCustomLoader(yaml.SafeLoader):
        pass

    class YamlCustomDumper(yaml.SafeDumper):
        pass

    def enum_constructor(loader, node):
        value = loader.construct_scalar(node)
        return StatusEnum[value]

    def enum_representer(dumper, data):
        return dumper.represent_scalar('!Status', data.name)

    yaml.SafeLoader.add_constructor('!Status', enum_constructor)
    yaml.SafeDumper.add_representer(StatusEnum, enum_representer)

    return YamlCustomLoader, YamlCustomDumper


YAML_STATUS_LOADER, YAML_STATUS_DUMPER = create_custom_yaml_loader_dumper_status_enum()

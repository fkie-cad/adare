import attrs
import base64
import yaml
from typing import ClassVar
from adarelib.event.event import Event, transform_data_to_event
from adarelib.testset.yaml.customloader import YAML_STATUS_DUMPER, YAML_STATUS_LOADER

@attrs.define
class WsCommand:
    command_type: ClassVar[str]
    _registry = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        command_type = getattr(cls, "command_type", None)
        if command_type:
            WsCommand._registry[command_type] = cls

    def encode(self):
        return self.command_type

    @classmethod
    def custom_decode(cls, data: str):
        raise NotImplementedError

    @classmethod
    def decode(cls, data: str):
        if ':' not in data:
            return None
        command_type, _ = data.split(':', 1)
        command_type = command_type.strip()
        subclass = cls._registry.get(command_type)
        if subclass:
            return subclass.custom_decode(data)
        raise ValueError(f"Unknown command_type '{command_type}'")

@attrs.define
class EXEC(WsCommand):
    command: str
    shell: bool
    cwd: str = ''
    command_type: ClassVar[str] = 'EXEC'

    def encode(self):
        command_dict = {
            'command': self.command,
            'shell': self.shell,
            'cwd': self.cwd,
        }
        command_base64 = base64.b64encode(yaml.dump(command_dict).encode()).decode()
        return f"{self.command_type}: {command_base64}"

    @classmethod
    def custom_decode(cls, data: str):
        if ':' not in data:
            return None
        _, command_base64 = data.split(':', 1)
        command_yaml = base64.b64decode(command_base64.strip()).decode()
        command_dict = yaml.safe_load(command_yaml)
        return cls(**command_dict)

@attrs.define
class DONE(WsCommand):
    name: str
    out_msg: str = ''
    err_msg: str = ''
    error: bool = False
    command_type: ClassVar[str] = 'DONE'

    def encode(self):
        data = {
            'name': self.name,
            'out_msg': self.out_msg,
            'err_msg': self.err_msg,
            'error': self.error
        }
        data_base64 = base64.b64encode(yaml.dump(data).encode()).decode()
        return f"{self.command_type}: {data_base64}"

    @classmethod
    def custom_decode(cls, data: str):
        if ':' not in data:
            return None
        _, data_base64 = data.split(':', 1)
        decoded_data = base64.b64decode(data_base64.strip()).decode()
        data_dict = yaml.safe_load(decoded_data)
        return cls(name=data_dict['name'], out_msg=data_dict['out_msg'], err_msg=data_dict['err_msg'], error=data_dict['error'])

@attrs.define
class LOG(WsCommand):
    name: str
    out_msg: str = ''
    err_msg: str = ''
    error: bool = False
    command_type: ClassVar[str] = 'LOG'

    def encode(self):
        data = {
            'name': self.name,
            'out_msg': self.out_msg,
            'err_msg': self.err_msg,
            'error': self.error
        }
        data_base64 = base64.b64encode(yaml.dump(data).encode()).decode()
        return f"{self.command_type}: {data_base64}"

    @classmethod
    def custom_decode(cls, data: str):
        if ':' not in data:
            return None
        _, data_base64 = data.split(':', 1)
        decoded_data = base64.b64decode(data_base64.strip()).decode()
        data_dict = yaml.safe_load(decoded_data)
        return cls(name=data_dict['name'], out_msg=data_dict['out_msg'], err_msg=data_dict['err_msg'], error=data_dict['error'])

@attrs.define
class EVENT(WsCommand):
    event: Event
    command_type: ClassVar[str] = 'EVENT'

    def encode(self):
        event_dict = attrs.asdict(self.event)
        yaml_content = yaml.dump(event_dict, Dumper=YAML_STATUS_DUMPER)
        encoded_data = base64.b64encode(yaml_content.encode()).decode()
        return f"{self.command_type}: {encoded_data}"

    @classmethod
    def custom_decode(cls, data: str):
        if ':' not in data:
            return None
        try:
            _, encoded_data = data.split(':', 1)
            decoded_data = base64.b64decode(encoded_data.strip()).decode()
            event_data = yaml.load(decoded_data, Loader=YAML_STATUS_LOADER)
            event = transform_data_to_event(event_data)
            return cls(event=event)
        except (ValueError, yaml.YAMLError) as e:
            raise ValueError(f"Failed to decode EVENT: {e}")

@attrs.define
class EXPERIMENT(WsCommand):
    name: str
    command_type: ClassVar[str] = 'EXPERIMENT'

    def encode(self):
        return f"{self.command_type}: {self.name}"

    @classmethod
    def custom_decode(cls, data: str):
        if ':' not in data:
            return None
        _, name = data.split(':', 1)
        return cls(name=name.strip())

@attrs.define
class ECHO(WsCommand):
    data: str
    command_type: ClassVar[str] = 'ECHO'

    def encode(self):
        return f"{self.command_type}: {self.data}"

    @classmethod
    def custom_decode(cls, data: str):
        if ':' not in data:
            return None
        _, data_str = data.split(':', 1)
        return cls(data=data_str.strip())

@attrs.define
class ECHOREPLY(WsCommand):
    data: str
    command_type: ClassVar[str] = 'ECHOREPLY'

    def encode(self):
        return f"{self.command_type}: {self.data}"

    @classmethod
    def custom_decode(cls, data: str):
        if ':' not in data:
            return None
        _, data_str = data.split(':', 1)
        return cls(data=data_str.strip())

@attrs.define
class BREAKPOINT(WsCommand):
    command_type: ClassVar[str] = 'BREAKPOINT'

    def encode(self):
        return f"{self.command_type}"

    @classmethod
    def custom_decode(cls, data: str):
        return cls()

@attrs.define
class BREAKPOINTRESOLVE(WsCommand):
    command_type: ClassVar[str] = 'BREAKPOINTRESOLVE'

    def encode(self):
        return f"{self.command_type}"

    @classmethod
    def custom_decode(cls, data: str):
        return cls()
# external imports
import ast

# configure logging
import logging

log = logging.getLogger(__name__)


class PyClassAttributeAnalyzer:
    root: ast.AnnAssign | ast.Assign

    def __init__(self, attribute: ast.AnnAssign | ast.Assign):
        self.root = attribute

    def get_attribute_as_dict(self) -> dict:
        attr_dict = {
            'name': '',
            'type': '',
            'value': ''
        }
        target = self.root.target
        if type(target) == ast.Name:
            attr_dict['name'] = target.id

        if hasattr(self.root, 'value'):
            attr_dict['value'] = self.root.value

        if type(self.root) == ast.AnnAssign:
            annotation = self.root.annotation
            if type(annotation) == ast.Name:
                attr_dict['type'] = annotation.id

        return attr_dict

    def get_type(self) -> str:
        attr_dict = self.get_attribute_as_dict()
        return attr_dict['type']

    def get_name(self) -> str:
        attr_dict = self.get_attribute_as_dict()
        return attr_dict['name']

    def get_value(self) -> str:
        attr_dict = self.get_attribute_as_dict()
        return attr_dict['value'].value

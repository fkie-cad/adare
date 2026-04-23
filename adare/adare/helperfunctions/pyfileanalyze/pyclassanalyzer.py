# external imports
import ast

# configure logging
import logging

# internal imports
from adare.helperfunctions.pyfileanalyze.pyclassattributeanalyzer import PyClassAttributeAnalyzer

log = logging.getLogger(__name__)


class PyClassAnalyzer:
    root: ast.ClassDef
    name: str
    parent_classes: list

    def __init__(self, class_def_node: ast.ClassDef):
        self.root = class_def_node
        self.name = class_def_node.name
        self.parent_classes = class_def_node.bases

    def get_attribute(self, attr_name: str) -> PyClassAttributeAnalyzer | None:
        for attr in self.root.body:
            if type(attr) in [ast.Assign, ast.AnnAssign]:
                attr: ast.Assign | ast.AnnAssign
                if PyClassAttributeAnalyzer(attr).get_attribute_as_dict()['name'] == attr_name:
                    return PyClassAttributeAnalyzer(attr)
        return None

    def get_method(self, method_name: str) -> ast.FunctionDef | None:
        return next(
            (
                method
                for method in self.root.body
                if type(method) == ast.FunctionDef and method.name == method_name
            ),
            None,
        )

    def get_attribute_as_dict(self, attr_name: str) -> dict:
        attr = self.get_attribute(attr_name)
        if attr:
            return attr.get_attribute_as_dict()
        return dict()

    def get_attributes(self) -> list[PyClassAttributeAnalyzer]:
        attributes = []
        for attr in self.root.body:
            if type(attr) in [ast.Assign, ast.AnnAssign]:
                attr: ast.Assign | ast.AnnAssign
                attributes.append(PyClassAttributeAnalyzer(attr))
        return attributes

    def get_attributes_as_dict(self) -> dict:
        attributes = dict()
        for attr in self.get_attributes():
            attr_dict = attr.get_attribute_as_dict()
            attributes[attr_dict['name']] = attr_dict
        return attributes

    def has_attribute(self, attr_name: str) -> bool:
        attribute_found = False
        for key in self.get_attributes_as_dict().keys():
            if key == attr_name:
                attribute_found = True
        return attribute_found

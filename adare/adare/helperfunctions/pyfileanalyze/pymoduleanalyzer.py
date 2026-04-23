# external imports
import ast

# configure logging
import logging
from pathlib import Path

# internal imports
from adare.helperfunctions.pyfileanalyze.load import load_as_ast_module
from adare.helperfunctions.pyfileanalyze.pyclassanalyzer import PyClassAnalyzer

log = logging.getLogger(__name__)


class PyDecoratedAttributeAdapter:
    """Adapter that mimics PyClassAttributeAnalyzer for decorator keyword arguments."""

    def __init__(self, value: str = '', type_name: str = ''):
        self._value = value
        self._type_name = type_name

    def get_value(self) -> str:
        return self._value

    def get_type(self) -> str:
        return self._type_name


class PyDecoratedParamAnalyzer:
    """Adapter that mimics PyClassAnalyzer for the synthetic parameter class of a @testfunction."""

    def __init__(self, func_name: str, func_node: ast.FunctionDef):
        self.name = f'_DecoratorParam_{func_name}'
        self._func_node = func_node

    def get_attributes_as_dict(self) -> dict:
        """Extract parameters from function signature, skipping 'ctx'."""
        attributes = {}
        args = self._func_node.args

        # Build list of (arg, default) pairs, right-aligned with defaults
        all_args = args.args
        defaults = args.defaults
        num_defaults = len(defaults)
        num_args = len(all_args)

        for i, arg in enumerate(all_args):
            if arg.arg == 'ctx' or arg.arg == 'self':
                continue

            type_name = ''
            if arg.annotation:
                if isinstance(arg.annotation, ast.Name):
                    type_name = arg.annotation.id
                elif isinstance(arg.annotation, ast.Constant):
                    type_name = str(arg.annotation.value)
                elif isinstance(arg.annotation, ast.Attribute):
                    type_name = ast.unparse(arg.annotation)

            default_value = ''
            default_index = i - (num_args - num_defaults)
            if default_index >= 0:
                default_node = defaults[default_index]
                if isinstance(default_node, ast.Constant):
                    default_value = default_node.value
                else:
                    default_value = ast.unparse(default_node)

            attributes[arg.arg] = {
                'name': arg.arg,
                'type': type_name,
                'value': default_value,
            }

        return attributes


class PyDecoratedFunctionAnalyzer:
    """Adapter that mimics PyClassAnalyzer for a @testfunction-decorated function."""

    def __init__(self, func_node: ast.FunctionDef, decorator_call: ast.Call):
        self._func_node = func_node
        self._decorator_call = decorator_call
        func_name = func_node.name
        self.name = f'_DecoratorTest_{func_name}'
        self._param_analyzer = PyDecoratedParamAnalyzer(func_name, func_node)

        # Extract keyword arguments from the decorator call
        self._kwargs = {}
        for kw in decorator_call.keywords:
            if kw.arg and isinstance(kw.value, ast.Constant):
                self._kwargs[kw.arg] = kw.value.value

    def has_attribute(self, attr_name: str) -> bool:
        if attr_name == 'parameter':
            return True
        if attr_name == 'testname':
            return 'name' in self._kwargs
        if attr_name == 'testdescription':
            return 'description' in self._kwargs
        return False

    def get_attribute(self, attr_name: str) -> PyDecoratedAttributeAdapter | None:
        if attr_name == 'testname':
            value = self._kwargs.get('name', '')
            return PyDecoratedAttributeAdapter(value=value)
        if attr_name == 'testdescription':
            value = self._kwargs.get('description', '')
            return PyDecoratedAttributeAdapter(value=value)
        if attr_name == 'parameter':
            return PyDecoratedAttributeAdapter(type_name=self._param_analyzer.name)
        return None

    def get_method(self, method_name: str) -> ast.FunctionDef | None:
        if method_name == 'test':
            return self._func_node
        return None

    def get_attributes_as_dict(self) -> dict:
        return self._param_analyzer.get_attributes_as_dict()


class PyModuleAnalyzer:
    module: ast.Module

    def __init__(self, python_file: Path):
        self.module = load_as_ast_module(python_file)

    def _get_decorated_testfunctions(self) -> list[PyDecoratedFunctionAnalyzer]:
        """Find all @testfunction-decorated functions in the module."""
        results = []
        for node in self.module.body:
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                # Handle bare name: @testfunction(...)
                if isinstance(decorator.func, ast.Name) and decorator.func.id == 'testfunction':
                    results.append(PyDecoratedFunctionAnalyzer(node, decorator))
                    break
                # Handle attribute access: @some_module.testfunction(...)
                if isinstance(decorator.func, ast.Attribute) and decorator.func.attr == 'testfunction':
                    results.append(PyDecoratedFunctionAnalyzer(node, decorator))
                    break
        return results

    def get_classes(self, parent: str = None) -> list[PyClassAnalyzer]:
        class_list: list = []
        for node in self.module.body:
            if isinstance(node,ast.ClassDef):
                node: ast.ClassDef
                if parent:
                    is_subclass = False
                    if hasattr(node, 'bases'):
                        for base in node.bases:
                            if hasattr(base, 'id'):
                                if base.id == parent:
                                    is_subclass = True
                            else:
                                log.warning(f'base has no id: {base}')
                        if is_subclass:
                            class_list.append(PyClassAnalyzer(node))
                else:
                    class_list.append(PyClassAnalyzer(node))

        # Include @testfunction-decorated functions when looking for BasicTest subclasses
        if parent == 'BasicTest':
            class_list.extend(self._get_decorated_testfunctions())

        return class_list

    def has_class(self, class_name: str) -> bool:
        classes = self.get_classes()
        return class_name in [cl.name for cl in classes]

    def get_class(self, class_name: str) -> PyClassAnalyzer | None:
        classes = self.get_classes()
        result = next((cl for cl in classes if cl.name == class_name), None)
        if result:
            return result

        # Check synthetic parameter classes from decorated functions
        for adapter in self._get_decorated_testfunctions():
            if adapter._param_analyzer.name == class_name:
                return adapter._param_analyzer
        return None

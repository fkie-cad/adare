# external imports
import ast
from pathlib import Path
from typing import Optional

# internal imports
from adarelib.helperfunctions.pyfileanalyze.load import load_as_ast_module
from adarelib.helperfunctions.pyfileanalyze.pyclassanalyzer import PyClassAnalyzer

# configure logging
import logging
log = logging.getLogger(__name__)


class PyModuleAnalyzer:
    module: ast.Module

    def __init__(self, python_file: Path):
        self.module = load_as_ast_module(python_file)

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
        return class_list

    def has_class(self, class_name: str) -> bool:
        classes = self.get_classes()
        return class_name in [cl.name for cl in classes]

    def get_class(self, class_name: str) -> Optional[PyClassAnalyzer]:
        classes = self.get_classes()
        return next((cl for cl in classes if cl.name == class_name), None)

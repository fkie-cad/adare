# external imports
import ast
from pathlib import Path

# configure logging
import logging
log = logging.getLogger(__name__)


def load_as_ast_module(path: Path) -> ast.Module:
    """
        load python file as an ast node
    """
    with open(path.as_posix(), "r") as f:
        module_node = ast.parse(f.read())
    return module_node

# external imports
import re

# configure logging
import logging
log = logging.getLogger(__name__)


def replace_var_in_match_regex(regex_match: re.Match, variables: dict):
    key = regex_match.group(1)
    if key in variables.keys():
        return re.escape(variables[key])
    else:
        log.error(f'variable {key} can\'t be replaced because it\'s not presend in the variable file')
        return ''


def replace_var_in_match_string(regex_match: re.Match, variables: dict):
    key = regex_match.group(1)
    if key in variables.keys():
        return variables[key]
    else:
        log.error(f'variable {key} can\'t be replaced because it\'s not presend in the variable file')
        return ''


def resolve_variable_in_string(string: str, variables: dict, regex: bool = False):
    regex_expr = r"{{[ ]*(.*?)[ ]*}}"
    if regex:
        return re.sub(regex_expr, lambda match: replace_var_in_match_regex(match, variables), string)
    return re.sub(regex_expr, lambda match: replace_var_in_match_string(match, variables), string)
# configure logging
import logging
log = logging.getLogger(__name__)

DTYPE_DEFAULTS = {
    int: 0,
    str: '',
    list: [],
    dict: {}
}


def get_value_if_missing_key(dictionary: dict, key, dtype=str, default=None):
    if key in dictionary.keys():
        return dictionary[key]
    else:
        if default:
            return default
        if dtype in DTYPE_DEFAULTS.keys():
            return DTYPE_DEFAULTS[dtype]
    return None

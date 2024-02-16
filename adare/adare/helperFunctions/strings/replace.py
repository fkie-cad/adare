def replace_multiple_strings(string, characters, replacement):
    for c in characters:
        string = string.replace(c, replacement)
    return string

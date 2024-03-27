
def make_string_path_safe(string: str) -> str:
    # Define a list of characters that are not safe for file paths
    unsafe_chars = [' ', '/', '\\', ':', '*', '?', '"', '<', '>', '|', '-']
    # Replace each unsafe character with an underscore
    for char in unsafe_chars:
        string = string.replace(char, '_')
    return string

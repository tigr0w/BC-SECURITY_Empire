import base64
import random
import string


def get_data_from_file(file_path: str):
    """
    Get data from file and base64 encode it
    """
    if file_path:
        with open(file_path, "rb") as stream:
            data = stream.read()

        return data


def get_random_string(length=-1, charset=string.ascii_letters):
    """
    Returns a random string of "length" characters.
    If no length is specified, resulting string is in between 6 and 15 characters.
    A character set can be specified, defaulting to just alpha letters.
    """
    if length == -1:
        length = random.randrange(6, 16)
    random_string = "".join(random.choice(charset) for x in range(length))
    return random_string

import re


def removeprefix(s, prefix):
    # Remove when we drop Python 3.8 support
    if s.startswith(prefix):
        return s[len(prefix) :]
    return s


def removesuffix(s, suffix):
    # Remove when we drop Python 3.8 support
    if s.endswith(suffix):
        return s[: -len(suffix)]
    return s


def is_valid_session_id(session_id):
    if not isinstance(session_id, str):
        return False
    return re.match(r"^[A-Z0-9]{8}$", session_id.strip()) is not None

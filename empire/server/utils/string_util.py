import re


def is_valid_session_id(session_id):
    if not isinstance(session_id, str):
        return False
    return re.match(r"^[A-Z0-9]{8}$", session_id.strip()) is not None

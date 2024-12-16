import re

SESSION_ID_PATTERN = re.compile(r"^[A-Z0-9]{8}$")
SLUGIFY_PATTERN = re.compile(r"[/_\-\s]")


def is_valid_session_id(session_id):
    if not isinstance(session_id, str):
        return False
    return SESSION_ID_PATTERN.match(session_id.strip()) is not None


def slugify(s: str):
    return SLUGIFY_PATTERN.sub("_", s).lower()

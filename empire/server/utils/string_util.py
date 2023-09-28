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

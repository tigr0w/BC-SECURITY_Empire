from empire.server.utils.string_util import removeprefix, removesuffix


def test_remove_prefix():
    assert removeprefix("empire", "emp") == "ire"
    assert removeprefix("empire", "empire") == ""
    assert removeprefix("empire", "empire1") == "empire"
    assert removeprefix("techteach", "tech") == "teach"


def test_remove_suffix():
    assert removesuffix("empire", "ire") == "emp"
    assert removesuffix("empire", "empire") == ""
    assert removesuffix("empire", "ire1") == "empire"
    assert removesuffix("techteach", "teach") == "tech"

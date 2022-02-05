from empire.server.utils.type_util import safe_cast


def test_safe_cast_string():
    assert safe_cast("abc", str) == "abc"


def test_safe_cast_int_from_string():
    assert safe_cast("1", int) == 1


def test_safe_cast_int_from_int():
    assert safe_cast(1, int) == 1


def test_safe_cast_float_from_float():
    assert safe_cast(1.0, float) == 1.0


def test_safe_cast_float_from_int():
    assert safe_cast(1, float) == 1.0


def test_safe_cast_float_from_string():
    assert safe_cast("1", float) == 1.0


def test_safe_cast_float_from_string_2():
    assert safe_cast("1.0", float) == 1.0


def test_safe_cast_boolean_from_string_true():
    assert safe_cast("True", bool) == True
    assert safe_cast("TRUE", bool) == True
    assert safe_cast("true", bool) == True


def test_safe_cast_boolean_from_string_false():
    assert safe_cast("False", bool) == False
    assert safe_cast("false", bool) == False
    assert safe_cast("FALSE", bool) == False

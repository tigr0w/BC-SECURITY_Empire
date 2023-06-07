from unittest.mock import MagicMock

from empire.server.utils.option_util import safe_cast, validate_options


def test_validate_options_required_strict_success():
    instance_options = {
        "enabled": {
            "Description": "Enable/Disable the module",
            "Required": True,
            "Value": "True",
            "SuggestedValues": ["True", "False"],
            "Strict": True,
        },
    }

    options = {
        "enabled": "True",
    }

    cleaned_options, err = validate_options(instance_options, options, None, None)

    assert cleaned_options == options


def test_validate_options_required_strict_failure():
    instance_options = {
        "enabled": {
            "Description": "Enable/Disable the module",
            "Required": True,
            "Value": "True",
            "SuggestedValues": ["True", "False"],
            "Strict": True,
        },
    }

    options = {
        "enabled": "Wrong",
    }

    cleaned_options, err = validate_options(instance_options, options, None, None)

    assert cleaned_options is None
    assert err == "enabled must be set to one of the suggested values."


def test_validate_options_required_empty_failure_doesnt_use_default():
    instance_options = {
        "Command": {
            "Description": "Command to run",
            "Required": True,
            "Value": "DEFAULT_VALUE",
            "SuggestedValues": [],
            "Strict": False,
        }
    }

    options = {
        "Command": "",
    }

    cleaned_options, err = validate_options(instance_options, options, None, None)

    assert cleaned_options is None
    assert err == "required option missing: Command"


def test_validate_options_required_missing_uses_default():
    instance_options = {
        "Command": {
            "Description": "Command to run",
            "Required": True,
            "Value": "DEFAULT_VALUE",
            "SuggestedValues": [],
            "Strict": False,
        }
    }

    options = {}

    cleaned_options, err = validate_options(instance_options, options, None, None)

    assert cleaned_options == {"Command": "DEFAULT_VALUE"}


def test_validate_options_casts_string_to_int_success():
    # Not going to bother testing every combo here since its already tested independently
    instance_options = {
        "Port": {
            "Description": "Port to listen on",
            "Required": True,
            "Value": "DEFAULT_VALUE",
            "SuggestedValues": [],
            "Strict": False,
            "Type": "int",
        }
    }

    options = {
        "Port": "123",
    }

    cleaned_options, err = validate_options(instance_options, options, None, None)

    assert cleaned_options == {"Port": 123}


def test_validate_options_missing_optional_field_no_defauls():
    instance_options = {
        "Command": {
            "Description": "Command to run",
            "Required": False,
            "Value": "",
            "SuggestedValues": [],
            "Strict": False,
        }
    }

    options = {}

    cleaned_options, err = validate_options(instance_options, options, None, None)

    assert cleaned_options == {"Command": ""}


def test_validate_options_with_file_not_found(db):
    instance_options = {
        "File": {
            "Description": "A File",
            "Required": True,
            "Strict": False,
            "Type": "file",
        }
    }

    options = {
        "File": "9999",
    }

    download_service_mock = MagicMock()
    download_service_mock.get_by_id.return_value = None

    cleaned_options, err = validate_options(
        instance_options, options, db, download_service_mock
    )

    assert cleaned_options is None
    assert err == "File not found for 'File' id 9999"


def test_validate_options_with_file(db, models):
    instance_options = {
        "File": {
            "Description": "A File",
            "Required": True,
            "Strict": False,
            "Type": "file",
        }
    }

    options = {
        "File": "9999",
    }

    download = models.Download(id=9999, filename="test_file", location="/tmp/test_file")
    download_service_mock = MagicMock()
    download_service_mock.get_by_id.return_value = download

    cleaned_options, err = validate_options(
        instance_options, options, db, download_service_mock
    )

    assert cleaned_options["File"] == download


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
    assert safe_cast("True", bool) is True
    assert safe_cast("TRUE", bool) is True
    assert safe_cast("true", bool) is True


def test_safe_cast_boolean_from_string_false():
    assert safe_cast("False", bool) is False
    assert safe_cast("false", bool) is False
    assert safe_cast("FALSE", bool) is False

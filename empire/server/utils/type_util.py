import typing


def safe_cast(option: typing.Any, expected_option_type: typing.Type) -> typing.Optional[typing.Any]:
    try:
        if expected_option_type is bool:
            return option.lower() in ['true', '1']
        return expected_option_type(option)
    except ValueError:
        return None

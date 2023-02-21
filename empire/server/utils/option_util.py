import typing

from empire.server.core.module_models import EmpireModuleOption


def safe_cast(
    option: typing.Any, expected_option_type: typing.Type
) -> typing.Optional[typing.Any]:
    try:
        if expected_option_type is bool:
            return option.lower() in ["true", "1"]
        return expected_option_type(option)
    except ValueError:
        return None


def convert_module_options(options: typing.List[EmpireModuleOption]) -> typing.Dict:
    """
    Since modules options are typed classes vs listeners/stagers/etc which are dicts, this function
    converts the options to dicts so they can use the same validation logic in validate_options.
    """
    converted_options = {}

    for option in options:
        converted_options[option.name] = {
            "Description": option.description,
            "Required": option.required,
            "Value": option.value,
            "SuggestedValues": option.suggested_values,
            "Strict": option.strict,
            "Type": option.type,
            "NameInCode": option.name_in_code,
        }

    return converted_options


def validate_options(instance_options: typing.Dict, params: typing.Dict):
    """
    Compares the options passed in (params) to the options defined in the
    class (instance). If any options are invalid, returns a Tuple of
    (None, error_message). If all options are valid, returns a Tuple of
    (options, None).

    Will also attempt to cast the options to the correct type using safe_cast.
    """
    options = {}
    # make a copy so that the original options are not modified
    params = params.copy()

    for instance_key, option_meta in instance_options.items():
        # Attempt to default a unset required option to the default value
        if (
            instance_key not in params
            and option_meta["Required"]
            and option_meta["Value"]
        ):
            params[instance_key] = option_meta["Value"]

        # If the required option still isn't set, return an error
        if option_meta["Required"] and (
            instance_key not in params
            or params[instance_key] == ""
            or params[instance_key] is None
        ):
            return None, f"required option missing: {instance_key}"

        # If strict, check that the option is one of the suggested values
        if (
            option_meta["Strict"]
            and params[instance_key] not in option_meta["SuggestedValues"]
        ):
            return (
                None,
                f"{instance_key} must be set to one of the suggested values.",
            )

        # If the option is set, attempt to cast it to the correct type
        casted, err = _safe_cast_option(
            instance_key, params.get(instance_key, ""), option_meta
        )
        if err:
            return None, err

        if option_meta.get("NameInCode"):
            options[option_meta["NameInCode"]] = casted
        else:
            options[instance_key] = casted

    return options, None


def set_options(instance, options: typing.Dict):
    """
    Sets the options for the listener/stager/plugin instance.
    """
    for option_name, option_value in options.items():
        instance.options[option_name]["Value"] = option_value


def _safe_cast_option(
    param_name, param_value, option_meta
) -> typing.Tuple[typing.Any, typing.Optional[str]]:
    option_type = type(param_value)
    expected_option_type = option_meta.get("Type") or type(option_meta["Value"])
    casted = safe_cast(param_value, expected_option_type)
    if casted is None:
        return (
            None,
            f"incorrect type for option {param_name}. Expected {expected_option_type} but got {option_type}",
        )
    else:
        return casted, None

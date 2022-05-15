import typing


def safe_cast(
    option: typing.Any, expected_option_type: typing.Type
) -> typing.Optional[typing.Any]:
    try:
        if expected_option_type is bool:
            return option.lower() in ["true", "1"]
        return expected_option_type(option)
    except ValueError:
        return None


def validate_options(instance, params: typing.Dict):
    """
    Compares the options passed in (params) to the options defined in the
    class (instance). If any options are invalid, returns a Tuple of
    (None, error_message). If all options are valid, returns a Tuple of
    (options, None).

    Will also attempt to cast the options to the correct type using safe_cast.
    """
    options = {}

    for instance_key, option_meta in instance.options.items():
        if instance_key in params:
            option_type = type(params[instance_key])
            expected_option_type = option_meta.get("Type") or type(option_meta["Value"])
            if option_type != expected_option_type:
                casted = safe_cast(params[instance_key], expected_option_type)
                if casted is None:
                    return (
                        None,
                        f"incorrect type for option {instance_key}. Expected {expected_option_type} but got {option_type}",
                    )
                else:
                    params[instance_key] = casted
            if (
                option_meta["Strict"]
                and params[instance_key] not in option_meta["SuggestedValues"]
            ):
                return (
                    None,
                    f"{instance_key} must be set to one of the suggested values.",
                )
            elif option_meta["Required"] and (
                params[instance_key] is None or params[instance_key] == ""
            ):
                return None, f"required option missing: {instance_key}"
            else:
                options[instance_key] = params[instance_key]
        elif option_meta["Required"]:
            return None, f"required option missing: {instance_key}"

    return options, None


def set_options(instance, options: typing.Dict):
    """
    Sets the options for the listener/stager/plugin instance.
    """
    for option_name, option_value in options.items():
        instance.options[option_name]["Value"] = option_value

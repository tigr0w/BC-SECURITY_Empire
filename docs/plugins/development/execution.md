# Execution

## Execute Function
The execute function is called when the plugin is executed via the API. The execute function is passed the following arguments:

* command - A dict of the command arguments, already parsed and validated by the core Empire code
* kwargs - Additional arguments that may be passed in by the core Empire code.
  * user - The user database object for the user executing the plugin. This is
    `None` for plugins run by the server via `auto_execute`, so dereference it
    defensively.
  * db - The database session object

There is no `plugin_options` keyword argument. Empire calls
`plugin.execute(cleaned_options, db=db, user=user)`, so the validated options are
`command`, the first positional parameter. See [Plugin Tasks](plugin-tasks.md).

### Error Handling

If an error occurs during the execution of the plugin and it goes unchecked,
the client will receive a 500 error.

There are two Exceptions that can be raised by the plugin execution function:
**PluginValidationException**: This exception should be raised if the plugin fails validation. This will return a 400 error to the client with the error message.
**PluginExecutionException**: This exception should be raised if the plugin fails execution. This will return a 500 error to the client with the error message.

```python
raise PluginValidationException("Error Message")
raise PluginExecutionException("Error Message")
```

### Response

Before the plugin's execute function is called, the core Empire code will validate the command arguments. If the arguments are invalid, the API will return a 400 error with the error message.

The execute function can return a String, a Boolean, or None.

* None - The execution will be considered successful.
* String - The string will be displayed to the user executing the plugin and the execution will be considered successful.
* Boolean - If the boolean is True, the execution will be considered successful. If the boolean is False, the execution will be considered failed.


```python
def execute(self, command, **kwargs):
    ...

    # Successful execution
    return None
    return "Execution complete"
    return True

    # Failed execution
    raise PluginValidationException("Error Message")
    raise PluginExecutionException("Error Message")
```

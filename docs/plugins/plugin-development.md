# Plugin Development

## Execute Function
The execute function is the entry point for the plugin. It is called when the plugin is executed via the API. The execute function is passed the following arguments:

* command - A dict of the command arguments, already parsed and validated by the core Empire code
* kwargs - Additional arguments that may be passed in by the core Empire code. Right now there are only two.
  * user - The user database object for the user that is executing the plugin
  * db - The database session object

If the plugin doesn't have `**kwargs`, then no kwargs will be sent. This is to ensure backwards compatibility with plugin pre-5.2.

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

The execute function can return a String, a Boolean, or a Tuple of (Any, String)

* None - The execution will be considered successful.
* String - The string will be displayed to the user executing the plugin and the execution will be considered successful.
* Boolean - If the boolean is True, the execution will be considered successful. If the boolean is False, the execution will be considered failed.

#### Deprecated

* Tuple - The tuple must be a tuple of (Any, String). The second value in the tuple represents an error message. The string will be displayed to the user executing the plugin and the execution will be considered failed.

This is deprecated.
Instead of returning an error message in a tuple, raise a `PluginValidationException` or `PluginExecutionException`.


```python
def execute(self, command, **kwargs):
    ...

    # Successful execution
    # return None
    # return "Execution complete"
    # return True

    # Failed execution
    # raise PluginValidationException("Error Message")
    # raise PluginExecutionException("Error Message")
    # return False, "Execution failed"
```

## Plugin Tasks
Plugins can store tasks. The data model looks pretty close to Agent tasks. This is for agent executions that:

1. Want to attach a file result
2. Need to display a lot of output, where notifications don't quite work
3. Has output you'll want to look back at later

```python
from empire.server.core.db import models

def execute(self, command, **kwargs):
    user = kwargs.get('user', None)
    db = kwargs.get('db', None)

    input = 'Example plugin execution.'

    plugin_task = models.PluginTask(
      plugin_id=self.info["Name"],
      input=input,
      input_full=input,
      user_id=user.id,
      status=models.PluginTaskStatus.completed,
    )

    db.add(plugin_task)
```

For an example of using plugin tasks and attaching files, see the [basic_reporting plugin](https://github.com/BC-SECURITY/Empire/blob/main/server/plugins/basic_reporting/basic_reporting.plugin).

## Notifications
Notifications are meant for time sensitive information that the user should be aware of.
In Starkiller, these get displayed immediately, so it is important not to spam them.

To send a notification, use the `plugin_service`.

```python
def register(self, mainMenu):
    self.plugin_service = mainMenu.pluginsv2

def execute(self, command, **kwargs):
    # Do something

    self.plugin_service.plugin_socketio_message(
        self.info["Name"], "Helo World!"
    )
```

## Using the database
Execute functions and hooks/filters are sent a SQLAlchemy database session. This does not need to be
opened or closed, as the calling code handles that. The database session is passed in
as a keyword argument.

```python
from sqlalchemy.orm import Session

def execute(self, command, **kwargs):
    user = kwargs.get('user', None)
    db: Session = kwargs.get('db', None)

    agents = self.main_menu.agentsv2.get_all(db)

    return "Execution complete"
```

It is important not to close the database session, as it will be used by the calling code and sent to other hooks/filters.

```python
from sqlalchemy.orm import Session
from empire.server.core.db import models

def on_agent_checkin(self, db: Session, agent: models.Agent):
    # Do something
    pass
```

When executing code outside of the execute function or hooks/filters, you will need to open a database session.
This means that you must handle your database session in the plugin. Using the Context Manager syntax
ensures the db session commits and closes properly.
```python
from empire.server.core.db.base import SessionLocal

def do_something():
    with SessionLocal.begin() as db:
        # Do the things with the db session
        pass
```

## Event-based functionality (hooks and filters)
This is outlined in [Hooks and Filters](./hooks-and-filters.md).

## Importing other python files

If you want to import other python files in your plugin, you can do so by importing
them relative to `empire.server.plugins`. For example, if you have a file called
`example_helpers.py` in the same directory as your plugin, you can import it like so:

```python
from empire.server.plugins.example import example_helpers
```

**Note**: Relative imports will not work. For example, the example plugin cannot
import `example_helpers.py` with `from . import example_helpers`.

## 4->5 Changes
Not a lot has changed for plugins in Empire 5.0. We've just added a few guard rails for better
stability between Empire versions.

The plugin interface is a guarantee that certain functionality will not be changed outside of major
Empire version updates (ie 4->5). So which functions are guaranteed? Any of the functions on the
`core/*_service` classes not prefixed with a `_`.

Does this mean you can't use `util` functions or modify state in other parts of the empire code?
No. In most cases you will be fine to do so. We as maintainers just can't keep track of any and
every thing a plugin may be doing and guarantee that it won't break in a minor/patch update.
This is no different than the way things were pre 5.0.

* Make sure `self.info` is a dict and not a tuple. A lot of plugins had a trailing comma that caused it to be interpreted as a tuple.
* Update `Author` to `Authors` and follow the new format (Link, Handle, Name)
* The execute plugin endpoint no longer automatically changes the state of the `self.options` dict inside the plugin. Instead, it sends validated parameters to the plugin as a dict and the plugin itself should decide whether it makes sense to modify the internal state or not.
* `plugin_socketio_message` was moved from `MainMenu` to `plugin_service`.
* Example conversion for a 5.0 plugin can be seen in [ChiselServer-Plugin](https://github.com/BC-SECURITY/ChiselServer-Plugin/compare/5.0)

## Future Work
* improved plugin logging -
  Give plugins individual log files like listeners have. Make those logs accessible via Starkiller.
* endpoint for installing plugins -
  A user would be able to provide the URL to a git repository and Empire would download and install the plugin.

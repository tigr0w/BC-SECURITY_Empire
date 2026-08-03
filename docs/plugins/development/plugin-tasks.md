# Plugin Tasks

Plugins can store tasks. The data model looks pretty close to Agent tasks. This is for agent executions that:

1. Want to attach a file result
2. Need to display a lot of output, where notifications don't quite work
3. Has output you'll want to look back at later

```python
from empire.server.core.db import models

def execute(self, command, **kwargs):
    db = kwargs['db']
    user = kwargs['user']

    # `command` is the validated options dict Empire passes positionally.
    # Build a copy for the task: `plugin_options` is a JSON column, so a `file`
    # option's Download has to become its id, and copying keeps a later edit to
    # `command` from rewriting the stored record.
    plugin_options = {
        key: value.id if isinstance(value, models.Download) else value
        for key, value in command.items()
    }

    task_input = 'Example plugin execution.'

    plugin_task = models.PluginTask(
      plugin_id=self.info.id,
      input=task_input,
      input_full=task_input,
      user_id=user.id if user is not None else None,
      status=models.PluginTaskStatus.completed,
      plugin_options=plugin_options,
    )

    db.add(plugin_task)
```

`plugin_id` must be `self.info.id`, not the plugin's display name. `PluginTask.plugin_id`
is a non-nullable foreign key to `plugins.id`, and that primary key is the plugin's
[id](README.md#plugin-name-and-id) — the slugified `name`, so a plugin named `My Plugin`
has the id `my_plugin`. Writing the display name, or a hardcoded constant that drifts from
`plugin.yaml`, produces rows under an id no plugin owns: MySQL raises a foreign-key error,
and SQLite does not enforce the constraint at all, so the rows land invisible to the
plugin's task history. Read the id off `self.info` rather than storing your own copy of it.

`plugin_options` is not a keyword argument. Empire calls
`plugin.execute(cleaned_options, db=db, user=user)`, so the validated options arrive as
`command`, the first positional parameter. Reading `plugin_options` out of `kwargs` yields
`None` and stores a task with no record of the options it ran with. `BasePlugin.execute`
assigns that kwarg on a local dict and then does nothing with it, so neither your override
nor a `super().execute(...)` call from it will populate anything — read `command`.

`plugin_options` is a JSON column, so every value you put in it must be JSON-serializable.
Options declared `Type: file` are the exception you have to handle: Empire resolves them to
a `models.Download` object, and storing one raises `TypeError: Object of type Download is
not JSON serializable` when the session flushes — after your plugin's work is done, so it
surfaces as an opaque 500. Store the download's id, as the sample does. Copy the dict rather
than assigning `command` directly, too: the column is serialized at flush, so any later
mutation of `command` would rewrite the record of what the task actually ran with.

`user` can be `None`. Plugins configured with `auto_execute` are run by the server with no
user attached, so dereference it defensively — `PluginTask.user_id` is nullable. `db` is
always passed, so index it directly and let a missing key raise rather than deferring the
failure to an `AttributeError` on `None`.

For an example of using plugin tasks and attaching files, see the [basic\_reporting plugin](https://github.com/BC-SECURITY/Empire/blob/main/empire/server/plugins/basic_reporting/basic_reporting.py).

## Statuses

Plugin tasks in Empire follow a similar lifecycle to agent tasks, with status updates providing key insights into the progress and outcomes of various plugin operations. Below are the possible statuses for plugin taskings along with descriptions and representative icons.

### Queued

* **Description**: The task is queued for the plugin. This status indicates that the task has been created and is waiting to be pulled by the server.
* **Icon**:&#x20;

### Started

* **Description**: The plugin has successfully pulled and started the tasking. This status signifies that the server has received the task and is either processing it or about to start processing.
* **Icon**:&#x20;

### Completed

* **Description**: The task has returned data successfully. This indicates that the plugin has finished executing the task and has returned the output.
* **Icon**:&#x20;

### Error

* **Description**: If an plugin reports an error for a task, it will return an ERROR status. This status allows users to identify tasks that did not execute as expected.
* **Icon**: )

### Continuous

* **Description**: A special class for modules like keylogging since they are handled differently on the server due to their continuous nature. These tasks do not have a definite end and run continuously until stopped.
* **Icon**:&#x20;

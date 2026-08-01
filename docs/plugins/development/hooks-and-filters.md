# Hooks and Filters

## Hooks and Filters

Hooks and filters are a function that a developer can implement that will be called when some event happens.

**Hooks** - Hooks are implemented to perform some side effect of an event happening. A hook does not need to return anything.

**Filters** - Filters are implemented to perform some modification of data after an event happens. A filter should return the modified arguments that it was given.

A minimal hook implementation.

```python
from sqlalchemy.orm import Session
from empire.server.core.hooks import hooks
from empire.server.core.db import models

def my_hook(db: Session, agent: models.Agent):
    """
    print to the console whenever an agent checks in.
    """
    print(f'New Agent Check in! Name: {agent.name}')


hooks.register_hook(hooks.AFTER_AGENT_CHECKIN_HOOK, 'checkin_logger_hook', my_hook)
```

A minimal filter implementation.

```python
from sqlalchemy.orm import Session
from empire.server.core.hooks import hooks
from empire.server.core.db import models

def my_filter(db: Session, task: models.AgentTask):
    """
    Reverses the output string of a tasking.
    """
    task.output = task.output[::-1]

    return task


hooks.register_filter(hooks.BEFORE_TASKING_RESULT_FILTER, 'reverse_filter', my_filter)
```

Each event has its own set of unique arguments. At the moment, the events are:

* AFTER_LISTENER_CREATED_HOOK

This event is triggered after the creation of a listener. Its arguments are (db: Session, listener: models.Listener).

* AFTER\_TASKING\_HOOK

This event is triggered after the tasking is queued and written to the database. Its arguments are (db: Session, tasking: models.Tasking)

* BEFORE\_TASKING\_RESULT\_HOOK/BEFORE\_TASKING\_RESULT\_FILTER

This event is triggered after the tasking results are received but before they are written to the database. Its arguments are (db: Session, tasking: models.Tasking) where tasking is the db record.

* AFTER\_TASKING\_RESULT\_HOOK

This event is triggered after the tasking results are received and after they are written to the database. Its arguments are (db: Session, tasking: models.Tasking) where tasking is the db record.

* AFTER\_AGENT\_CHECKIN\_HOOK

 This event is triggered after the agent has completed the stage2 of the checkin process, and the sysinfo has been written to the database. Its arguments are (db: Session, agent: models.Agent)

* AFTER\_AGENT\_CALLBACK\_HOOK

This event is triggered each time an agent calls back to the C2 server, after the sysinfo has been written to the database. Its arguments are (db: Session, agent_id: str)

* AFTER\_TAG\_CREATED\_HOOK

This event is triggered after a brand-new tag row is created in the tag registry. It does NOT fire when an existing tag is attached — only when the tag itself is created. Its arguments are (db: Session, tag: models.Tag). When a tag is created as part of attaching it to an entity, `AFTER_TAG_ATTACHED_HOOK` fires immediately afterwards with that entity, so this event stays a pure registry-creation signal.

* AFTER\_TAG\_ATTACHED\_HOOK

This event is triggered every time a tag is attached to an entity — an agent, agent task, listener, plugin task, credential, or download — whether the tag was newly created or already existed. This is the "an entity was tagged" signal. It does NOT fire on an idempotent re-attach of a tag the entity already carries. Its arguments are (db: Session, tag: models.Tag, taggable) where `taggable` is the entity the tag was attached to.

* AFTER\_TAG\_UPDATED\_HOOK

This event is triggered after a tag is edited (rename, recolor, or description change). Its arguments are (db: Session, tag: models.Tag) — tag edits are global and have no associated entity.

* AFTER\_CHAT\_MESSAGE\_HOOK

This event is triggered after a chat message is persisted to the general chat channel. Its arguments are (db: Session, message: models.ChatMessage). The message is expunged before the session commits, so the hook receives a fully-populated detached instance and can read its attributes without a `DetachedInstanceError`. Like the tasking and callback hooks, it is fired with `None` as the session argument so the async dispatch opens its own managed session.

_The number of events at the moment is very minimal. If there's an event that you would like added, open an issue on the GitHub repo, come chat in our Discord, or put up a pull request._

### Real World Examples

Empire utilizes both filters and hooks itself that can be used as a reference.

* The Powershell agent was updated to return JSON for some of the base shell commands. There are filters for `ls`, `ps`, `route`, and `ifconfig` that convert the JSON response to a table before it gets stored in the database.
* There is a hook implemented for the `ps` command that converts the results of `ps` from Powershell and Python agents into database records.
* An example plugin that utilizes hooks is the [Twilio-Plugin](https://github.com/BC-SECURITY/Twilio-Plugin) which sends an operator a text message when an agent checks in.

Future enhancements:

*   Since hooking the agent results events will invoke hooks on every single tasking result,
    we'd like to implement something that is more module specific. For example, a module that needs to store credentials, such as Mimikatz, could have a `on_response` function in its `.py` file that is invoked specifically when that module returns.

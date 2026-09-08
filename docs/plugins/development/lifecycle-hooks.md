# Lifecycle Hooks

## on_load

The `on_load` function is called when the plugin is loaded into memory.
```python
@override
def on_load(self, db):
    print("Plugin loaded")
```

### Registering a listener template

Plugins can contribute their own listener templates via `self.register_listener(instance, name=None)`, which registers an already-instantiated `Listener(main_menu)` and returns the slugified key it was registered under. Call it from `on_load` so the template exists before `ListenerService.start_existing_listeners` runs on Empire startup.

```python
@override
def on_load(self, db):
    self.register_listener(MyListener(self.main_menu))
```

Remove it with `self.main_menu.listenertemplatesv2.unregister_listener_template(name)`, e.g. from `on_unload`. This does not stop any listeners already instantiated from the template — stop those first.

## on_unload

The `on_unload` function is called when the plugin is unloaded from memory.
```python
@override
def on_unload(self, db):
    print("Plugin unloaded")
```

## on_start

The `on_start` function is called when the plugin is started.
```python
@override
def on_start(self, db):
    print("Plugin started")
```

`self.enabled` is already `True` when `on_start` runs, so a background thread it
spawns can use `while self.enabled` as its run guard.

## on_stop

The `on_stop` function is called when the plugin is stopped.
```python
@override
def on_stop(self, db):
    print("Plugin stopped")
```

`self.enabled` is already `False` when `on_stop` runs, on every path, so a
`while self.enabled` loop sees the stop.

`on_stop` is also called for **every** loaded plugin when Empire shuts down,
when an operator calls `POST /api/v2/plugins/reload`, and when a plugin fails
partway through loading — including plugins that were never started. Write it so
it is safe to call against a plugin that never ran (guard the handles `on_start`
would have set); the failed-load case reaches it with only `on_load` having run.
Reload is the case worth designing for: Empire builds fresh plugin objects
immediately afterwards, so anything `on_stop` fails to tear down keeps running
alongside its replacement.

If `on_stop` raises during shutdown or reload, Empire logs it and moves on
(`on_unload` still runs), but whatever it had not released yet stays leaked.

When a plugin is *disabled* through the API instead, an `on_stop` exception
propagates to the caller as a 500 and the request's transaction rolls back, so
the stored `enabled` flag keeps its previous value and the operator can retry.
The plugin object stays `enabled = False` regardless — your worker has already
seen the stop, and Empire will not accept plugin commands for it until a later
enable succeeds.

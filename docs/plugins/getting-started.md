# Plugins Getting Started

This page will walk you through the process of creating a plugin for Empire using
the hello world plugin as an example. The hello world plugin is an example plugin
that can be found in the `empire/server/plugins/example` directory.

```
empire/server/plugins/example
├── __init__.py
├── example.py
└── plugin.yaml
```

The `plugin.yaml` configuration will likely be expanded on in the future, but for now
it only contains one property: `main`. This is the name of the python file within the
plugin's directory that contains the plugin class.

```yaml
main: example.py
```

The `example.py` file contains the plugin class. The class must be named `Plugin`
and must inherit from `empire.server.common.plugins.BasePlugin`.

```python
class Plugin(BasePlugin):
    ...
```

To get into the details of the plugin, move onto the [plugin development](./plugin-development.md) page.

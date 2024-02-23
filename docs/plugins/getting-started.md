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

## plugin.yaml
```yaml
name: example
authors:
  - name: Author 1
    handle: '@author1'
    link: https://twitter.com/author1
description: |
  A description of what the module does and how it works.
# Software and tools that from the MITRE ATT&CK framework (https://attack.mitre.org/software/)
software:
# Techniques that from the MITRE ATT&CK framework (https://attack.mitre.org/techniques/enterprise/)
techniques:
  - TXXXX
  - TXXXX
comments:
  - Any additional comments about the module.
# The entry point for the plugin. The file that contains the `Plugin` class.
main: example.py

```

The `example.py` file contains the plugin class. The class must be named `Plugin`
and must inherit from `empire.server.common.plugins.BasePlugin`.

```python
class Plugin(BasePlugin):
    ...
```

To get into the details of the plugin, move onto the [plugin development](./plugin-development.md) page.

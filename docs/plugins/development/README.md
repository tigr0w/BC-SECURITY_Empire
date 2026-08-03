# Plugin Development

## Getting Started

The hello world plugin is an example plugin
that can be found in the `empire/server/plugins/example` directory.

```
empire/server/plugins/example
├── __init__.py
├── example.py
├── example_helpers.py
└── plugin.yaml
```

## plugin.yaml
```yaml
name: example
authors:
  - name: Author 1
    handle: '@author1'
    link: https://twitter.com/author1
# Software and tools that from the MITRE ATT&CK framework (https://attack.mitre.org/software/)
software:
# Techniques that from the MITRE ATT&CK framework (https://attack.mitre.org/techniques/enterprise/)
techniques:
  - TXXXX
  - TXXXX
# The entry point for the plugin. The file that contains the `Plugin` class.
main: example.py
# Extra dependencies that the plugin requires.
# Empire will not automatically install these dependencies, but
# will check if they are installed before running the plugin.
# Starkiller may tell the user to install these dependencies when it is installed via the marketplace.
python_deps:
  - requests>=2.25.1
  - pyyaml
```

### Plugin name and id

Choose `name` carefully — everything Empire uses to identify your plugin is derived from
it. The plugin's **id** is `slugify(name)` — lowercased, with `/`, `_`, `-` and whitespace
replaced by underscores — so `My Plugin` has the id `my_plugin`. That id is the primary key
of the `plugins` table, the key for per-plugin `config.yaml` entries, and the name of both
the directory and the Python package a marketplace install loads your plugin as. Two rules
follow:

* **Don't put a `.` in `name`.** `slugify` leaves dots alone, so `My.Plugin` yields the id
  `my.plugin`, which Python reads as a nested package path and which no install can load.
* **Don't pick a name whose id collides with an installed Python distribution** (`mcp`,
  `requests`, …). site-packages wins the lookup and shadows your plugin's package.

Both are silent in a checkout and only fail once installed from a registry — see
[Imports](imports.md) for why. Name your plugin directory the same as the id while
developing so your local layout matches a real install.

The `example.py` file contains the plugin class. The class must be named `Plugin`
and must inherit from `empire.server.core.plugins.BasePlugin`.

```python
class Plugin(BasePlugin):
    ...
```

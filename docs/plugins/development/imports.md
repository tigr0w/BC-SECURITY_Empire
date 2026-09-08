# Importing other python files

Add a `__init__.py` file to your plugin directory to make it a package.

If you want to import other python files in your plugin, you can do so by importing
them relative to your entrypoint.

For example, if you have a file called
`example_helpers.py` in the same directory as your plugin, you can import it like so:

```python
from . import example_helpers
```

## Why relative, and why your plugin's id matters

Relative imports are not a style preference. An absolute import of your own
modules — `from empire.server.plugins.my_plugin import example_helpers` —
resolves only while the plugin sits inside an Empire checkout. A plugin
installed from a registry does not: Empire unpacks it to
`<DATA_DIR>/plugins/marketplace/<plugin id>/` and loads it as a **top-level**
package named after that directory, so `empire.server.plugins.my_plugin` does
not exist and every such import raises. Empire logs the failure and records it
as a `load_error` on the plugin instead of crashing, so the symptom is a plugin
that never loads rather than a visible break — and your own test suite will not
catch it if you develop in a checkout, because in-tree is the one layout where
those imports do resolve.

The package name always comes from the plugin's **directory**, never from
`plugin.yaml` — Empire derives it from the directory holding your entrypoint and
makes it importable by appending that directory's **parent** to `sys.path`. In a
checkout that is whatever you called the folder; a marketplace install puts the
plugin in a directory named after its [id](README.md#plugin-name-and-id), so
there it is the id that names your package. And it appends rather than prepends,
so the entry lands *behind* `site-packages`. Two consequences for how you choose
`name`:

* **The id must not collide with an installed distribution.** If your id is
  `mcp` and something in Empire's environment also provides a top-level `mcp`
  package — your own dependency, or a transitive one you never named —
  site-packages wins the lookup. Your plugin's package name is shadowed, and its
  relative imports, which resolve through that package name, bind to the
  third-party package instead of your files. The failure looks like
  `ImportError: cannot import name 'example_helpers' from 'mcp'`.
* **Avoid `.` in `name`.** `slugify` does not touch dots, so `My.Plugin` yields
  the id `my.plugin`, which Python reads as a nested package path. The first
  relative import then fails with `ModuleNotFoundError: No module named 'my'`.

Because the package name is the directory name, name your plugin directory the
same as the id while developing. Nothing enforces it in a checkout — Empire takes
the id from `plugin.yaml`, not from the directory — but a marketplace install
always uses the id, so matching it locally is what makes your development layout
behave like a real one.

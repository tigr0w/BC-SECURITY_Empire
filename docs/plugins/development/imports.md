# Importing other python files

If you want to import other python files in your plugin, you can do so by importing
them relative to `empire.server.plugins`. For example, if you have a file called
`example_helpers.py` in the same directory as your plugin, you can import it like so:

```python
from empire.server.plugins.example import example_helpers
```

**Note**: Relative imports will not work. For example, the example plugin cannot
import `example_helpers.py` with `from . import example_helpers`.

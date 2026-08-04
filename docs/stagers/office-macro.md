# Office Macro

## Overview

`windows/macro` and `osx/macro` generate MS Office macros that run Empire's stage0 launcher when the document is opened (or closed). Both embed the launcher payload as a base64/string-chunked blob inside VBA and trigger it from a `Sub`/`Function` bound to the document lifecycle.

## Compatibility

- **`windows/macro`** — compatible with Office **97-2003 and 2007+** file types. `DocType` selects `word` or `excel`; `Trigger` selects `autoopen` or `autoclose` (mapped to `AutoOpen`/`AutoClose` for Word, `Workbook_Open`/`Workbook_BeforeClose` for Excel). Supports `Language` = `powershell`, `ironpython`, or `csharp` for the embedded launcher.
- **`osx/macro`** (internal name `AppleScript`) — targets **newer versions of Office for Mac**. Its `Version` option distinguishes Mac Office **older than 15.26** (`"old"`) from **15.26 and newer** (`"new"`, the default), which changes the VBA `Declare` syntax used to call into `libc.dylib` (`system()` for old, `popen()`-based `system` alias for new). Only `Language = python` is supported.
- **`multi/macro`** — a single cross-platform macro that embeds *both* a Windows PowerShell payload and a Mac Python payload behind `#If Mac Then ... #Else ... #End If` conditional compilation, detecting the host OS at runtime; compatible with Office **97-2016, including Mac 2011 and 2016 (sandboxed)**. It also supports an optional `PixelTrackURL` that is pinged (tagged `Mac2011`, `Mac2016`, or `Windows`) so an operator can tell which OS/version opened the document.

## How It Works

For `windows/macro`:

1. A stage0 launcher is generated for the chosen `Language` (`generate_exe_oneliner_routed` for `csharp`/`ironpython`, `generate_launcher` for `powershell`), applying `Bypasses`, `Base64` encoding, and (PowerShell only) `Obfuscate`/`ObfuscateCommand`.
2. The launcher is split into ~50-character chunks and assembled into a VBA string-concatenation payload.
3. The payload is wrapped in a `Sub`/`Function` pair matching the selected `Trigger`/`DocType`, then executed via `CreateObject("WScript.Shell").Run(...)`.
4. If `OutlookEvasion` is enabled, WMI checks against a specific `IdentifyingNumber` and known sandbox disk sizes are prepended, causing the macro to bail out (`End`) inside known sandbox VMs before running the payload.

For `osx/macro`:

1. A Python stage0 launcher is generated and base64-encoded (`generate_launcher(language="python", encode=True)`).
2. The launcher is chunked into a VBA string and wrapped in `Auto_Open`/`Document_Open` subs guarded by `#If Mac Then`.
3. Execution happens via a `Declare`d call into `libc.dylib`'s `system`/`popen`, running `echo "import sys,base64;exec(base64.b64decode(...))" | python3 &` — no on-disk script is written.

`multi/macro` follows the same chunk-and-embed pattern for both a PowerShell payload (Windows branch, executed via WMI `Win32_Process.Create`) and a Python payload (Mac branch, via `libc.dylib`), selected at runtime by the `#If Mac Then` preprocessor directive rather than at generation time.

# Reflective DLL

## Overview

`windows/dll` ("DLL Launcher") generates a **PowerPick reflective DLL** carrying stager code, meant to be injected into a process's memory rather than run as a normal on-disk DLL. It works by patching a prebuilt reflective-loader DLL template with the base64-decoded stage0 launcher.

## Compatibility

Windows only. The `Arch` option (`x64` default, or `x86`) must match the prebuilt template used — Empire ships separate `ReflectivePick_x64_orig.dll` and `ReflectivePick_x86_orig.dll` files under `data/misc/`, and the generated DLL's architecture must match the target process's bitness. `Language` supports `powershell` (default), `ironpython`, or `csharp` for the embedded launcher.

## How It Works

1. `generate()` verifies the target `Listener` exists (raises `StagerGenerationException` if not).
2. A stage0 launcher is generated for the chosen `Language`: `generate_exe_oneliner_routed` for `csharp`/`ironpython`, or `generate_launcher` for `powershell` — honoring `Bypasses`, `UserAgent`, `Proxy`/`ProxyCreds`, and (PowerShell only) `Obfuscate`/`ObfuscateCommand`. Combining `Obfuscate` with a `launcher`-type `ObfuscateCommand` is explicitly rejected for this stager ("LAUNCHER obfuscation cannot be used in the dll stager").
3. The base64 payload is extracted from the generated launcher command.
4. `generate_dll(launcher_code, arch)` reads the matching `ReflectivePick_{x86|x64}_orig.dll` template, locates a UTF-16 `"Invoke-Replace"` placeholder inside it, and splices the base64-decoded launcher bytes into that location — producing a DLL that reflectively loads and runs the embedded PowerShell code entirely in memory.

The resulting DLL is intended to be delivered via a reflective DLL injection technique (loaded directly into a target process's memory), not executed conventionally (e.g. via `rundll32`).

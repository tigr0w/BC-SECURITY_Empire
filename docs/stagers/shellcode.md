# Shellcode

## Overview

`windows/shellcode` ("Shellcode Launcher") and `osx/shellcode` ("Shellcode launcher") both produce position-independent shellcode stagers, but they get there differently: the Windows stager is **Donut-based**, while the macOS stager is a small hand-written syscall stub.

## Compatibility

- **`windows/shellcode`** — Windows. `Language` supports `powershell`, `csharp`, or `python` (default `powershell`); `DotNetVersion` is `net35` or `net40`; `Architecture` is `x86`, `x64`, or `both` (default `both`).
- **`osx/shellcode`** — macOS. `Language` only supports `python`; `Architecture` is `x86` or `x64` (default `x64`). The source notes the generated shellcode "contains NULL bytes, may need to be encoded."

## How It Works

**Windows (`windows/shellcode`)** — uses Empire's Donut integration (the `donut-shellcode` Python module) throughout:

1. A raw (unencoded) stage0 launcher is generated via `generate_launcher()`, honoring `Bypasses` and (PowerShell only) `Obfuscate`/`ObfuscateCommand`.
2. Depending on `Language`:
   - `powershell` — the launcher is first compiled into an EXE via the `CSharpPS` path, then that EXE is converted to shellcode with `donut_create()`.
   - `csharp` — `generate_launcher()` itself already returns a compiled Sharpire executable for this language (the `csharp` path has no separate launcher stage — see [C# Stagers](csharp.md)), so that executable's file path is passed straight to `donut_create()` as the input file (`Architecture` maps to Donut's arch codes: `x86`→1, `x64`→2, `both`→3).
   - `python` — the launcher is compiled into an EXE via the `CSharpPy`/IronPython path, then Donut-converted, same as the `powershell` path.
3. If the optional `donut-shellcode` module isn't installed, generation fails with an explicit error rather than falling back silently.

**macOS (`osx/shellcode`)** — does **not** use Donut:

1. An encoded Python stage0 launcher is generated via `generate_launcher()`.
2. A small hand-written raw shellcode stub for the selected architecture (x86 or x64) is assembled: it calls `setuid(0)` then `execve("/bin/sh", ["-c", <payload>, NULL])` via direct syscalls, with the base64-encoded Python one-liner concatenated in as the command string.
3. No compilation or Donut conversion is involved — the returned bytes are the raw syscall shellcode plus the embedded launcher string.

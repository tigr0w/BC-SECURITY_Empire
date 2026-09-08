# C# Stagers

## Overview

`windows/csharp_exe` ("C# PowerShell Launcher") generates a C# solution with embedded stager code that is compiled into a Windows executable via the bundled Empire-Compiler (Roslyn). Its `Language` option picks one of three compiled paths, each backed by a different compiler-template YAML:

| Language | Template | What gets compiled |
|----------|----------|---------------------|
| `powershell` | `CSharpPS.yaml` | A C# wrapper that embeds a PowerShell launcher as a `launcher.txt` resource and runs it in-process via `System.Management.Automation.PowerShell.Create().AddScript(...).Invoke()`. |
| `ironpython` | `CSharpPy.yaml` | A C# wrapper bundling IronPython (`IronPython.dll`, `Microsoft.Scripting.dll`, etc.) that embeds an IronPython launcher as `launcher.txt` and runs it via `Empire.Agent(script)`. |
| `csharp` (default) | `Sharpire.yaml` | Not a wrapper — the listener renders `Sharpire.yaml`'s template directly with the live session parameters (host address, staging key, malleable profile, working hours, kill date, delay, jitter, lost limit, default response, and the agent's key-pair bytes) to produce a fully native, self-contained compiled C# Empire agent. |

All three compiler templates are also reused directly by other code paths beyond this stager: the Donut shellcode generator ([Shellcode](shellcode.md)) compiles through `CSharpPS`/`CSharpPy` before converting the result to shellcode, and the HTTP(S) listeners' own `ironpython` stage0 path compiles through `CSharpPy` to serve a ready-to-run executable.

## Compatibility

Windows / .NET only. Compatible .NET versions differ by template:

- `CSharpPS`: Net40, Net35
- `CSharpPy`: Net40
- `Sharpire`: Net40, Net45

The `windows/csharp_exe` stager itself exposes a `DotNetVersion` option (`net40` / `net45`) that is passed through to the compiler for the `powershell`/`ironpython` paths.

## How It Works

1. The operator picks `Language`, `Listener`, `DotNetVersion`, and (for `powershell`) `Obfuscate` / `ObfuscateCommand`, plus `UserAgent`, `Proxy`, `ProxyCreds`, `Bypasses`, and `OutFile` (defaults to `Sharpire.exe`). `Staged` (default `True`) only matters for `powershell`/`ironpython`: unchecking it swaps the normal staged launcher for `generate_stageless()` (the same stageless-agent mechanism as [`multi_generate_agent`](multi_generate_agent.md)) instead of a stage0 launcher. It has no effect when `Language` is `csharp`, since the compiled Sharpire agent is always self-contained.
2. For `powershell` or `ironpython`, a normal stage0 launcher is generated first via `generate_launcher()` — encoding, `Bypasses`, and (PowerShell only) Invoke-Obfuscation via `ObfuscateCommand` are applied here, the same as any other launcher.
3. That launcher is embedded into the matching C# solution (`CSharpPS` for PowerShell, `CSharpPy` for IronPython) and handed to `EmpireCompiler`, which invokes Roslyn to produce the executable for the requested `.NET` version.
4. For `csharp`, the listener instead renders `Sharpire.yaml` with the live session parameters and compiles it directly — there is no intermediate launcher, since Sharpire is itself the compiled agent.
5. Passing `--confuse` to `EmpireCompiler` runs the compiled output through **ConfuserEx 2**. Note that the per-stager `Obfuscate` checkbox is scoped to the `powershell` path only (`DependsOn: Language == powershell`); obfuscation of the `csharp`/`ironpython` compiled output is instead controlled by the global C# obfuscation config (`ObfuscationService.get_obfuscation_config(db, "csharp")`).

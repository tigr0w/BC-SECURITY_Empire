# Bypasses

Bypasses are stored in yamls found in `/empire/server/bypasses/` and use a similar formatting as modules. Each bypass declares a `language:` field — `powershell` bypasses (the original use case) require a minimum PowerShell version of 3, and `python` bypasses are concatenated into Python launchers when the requested language matches.

When Empire first loads, it writes the data from the yamls to the database. Bypasses can then be edited via Starkiller or the API, with the changes going only to the version stored in the database.

A bypass is only injected into a launcher when its `language:` matches the launcher's language; mismatches are skipped and logged.

## Bundled Bypasses

| Name | Language | Purpose |
| --- | --- | --- |
| `etw` | powershell | Disables ETW logging via reflection |
| `mattifestation` | powershell | Reflective AMSI disable (PS session) |
| `Liberman` | powershell | AMSI buffer patching |
| `RastaMouse` | powershell | AMSI memory patching |
| `ScriptBlockLogBypass` | powershell | Disables ScriptBlock logging |
| `SafeChecksPS` | powershell | Aborts launcher on PS <3 and disables `Expect: 100-Continue` |
| `SafeChecksPython` | python | Exits the launcher on macOS hosts running Little Snitch |

`SafeChecksPS` and `SafeChecksPython` replace the legacy per-stager `SafeChecks` option, which was removed in 7.0. Users who relied on the previous default-on behavior must now opt in explicitly by adding the relevant name to a stager's `Bypasses` parameter.

## Default Bypasses

Default bypasses can be configured in the `config.yaml` file under `database.defaults.bypasses`. These bypasses will be automatically applied to stagers and modules when they are generated. The default bypasses are specified as a list of bypass names.

```yaml
database:
  defaults:
    bypasses:
      - mattifestation
      - etw
```

### Example Bypasses YAML

```yaml
name: ''
authors:
  - ''
description: ''
comments:
  - ''
language: powershell
min_language_version: '3'
script: ''
```

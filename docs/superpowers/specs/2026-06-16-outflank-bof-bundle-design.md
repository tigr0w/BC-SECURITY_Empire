# Outflank C2-Tool-Collection BOF bundle — design

**Date:** 2026-06-16
**Branch target:** `7.0-dev`
**Closes:** #1433, #1434, #1438, #1439, #1440, #1442 — defers #1441 (RemotePipeList)
**Pinned SHA:** `e371a38c717edaf1650923575ab33bee0dd3e0ee`

## Summary

Add seven Beacon Object File (BOF) modules ported from the Outflank
[C2-Tool-Collection](https://github.com/outflanknl/C2-Tool-Collection) to Empire's
in-tree BOF module set. Each module follows the existing TrustedSec-BOF pattern
already in the repo (`bof/situational_awareness/netview.yaml` and siblings): a YAML
descriptor pointing at pre-compiled `.o` objects vendored under
`empire/server/data/module_source/bof/<category>/<tool>/`.

This is a single-repo change. No Empire-Compiler (Roslyn) work is involved.

## License gate

The upstream repo has **no LICENSE file** — under default copyright that is
all-rights-reserved, not public domain. Every source issue lists "confirm a
permissive license before vendoring" as its first acceptance criterion.

**Resolution:** BC-Security has confirmed it has permission to vendor from the
Outflank C2-Tool-Collection (decision recorded by the project owner during
brainstorming, 2026-06-16). Each module's `comments:` block cites the upstream repo
URL and the pinned commit SHA so provenance is auditable.

**Merge gate:** The PR must link to a durable written permission artifact (a signed
email from an Outflank maintainer, an upstream GitHub issue comment granting
permission, or a NOTICE file entry added in this PR) before it can merge. If no
written grant can be obtained, the PR falls back to the runtime-fetch installer
track (#1470) — which does not vendor copyrighted objects in-tree — instead of
merging. The implementer must confirm which artifact exists and link it in the PR
body before requesting review.

## Scope

Seven BOF modules (see FindObjects note below). RemotePipeList (#1441) is
**explicitly out of scope**: it is a .NET tool (the issue specifies `Form factor:
csharp`, `Two-repo required: Yes`, target `csharp/situational_awareness/`), built
via Roslyn rather than mingw, and belongs in a future C# bundle.

| Issue | Module | Empire path | Category | `format_string` | Notes |
|-------|--------|-------------|----------|-----------------|-------|
| #1438 | reconad | `bof/situational_awareness/reconad` | situational_awareness | `ZZZiiZ` | ADSI AD object/attribute enumeration |
| #1439 | domaininfo | `bof/situational_awareness/domaininfo` | situational_awareness | `''` | Arg-less; BOF is Cobalt-Strike–style inline enumeration. Cite existing PowerView overlap in PR. |
| #1440 | smbinfo | `bof/situational_awareness/smbinfo` | situational_awareness | `Z` | Remote SMB/host info |
| #1442 | findmodule | `bof/situational_awareness/findmodule` | situational_awareness | `Z` | Find loaded module across processes (from FindObjects upstream dir). Cite overlap with existing `findLoadedModule` (TrustedSec, `zz`, two-arg) in PR — Outflank variant takes a single wide-string arg and omits the process-name filter. |
| #1442 | findprochandle | `bof/situational_awareness/findprochandle` | situational_awareness | `Z` | Find handle by name across processes (from FindObjects upstream dir) |
| #1434 | startwebclient | `bof/lateral_movement/startwebclient` | lateral_movement | `''` | Starts the WebClient service (WebDAV coercion enabler); arg-less |
| #1433 | lapsdump | `bof/credentials/lapsdump` | credentials | `Z` | BOF form distinct from PS `get_lapspasswords` (in-process, avoids AMSI/PS surface). Cite in PR. |

**FindObjects upstream directory contains two independent BOFs**, not one:
`FindModule.c` and `FindProcHandle.c` each define their own `go()` entry point and
shared helper functions (`BeaconPrintToStreamW`, `IsElevated`, etc.). Partial-link
(`ld -r`) fails with duplicate symbol errors on both arches (confirmed empirically at
the pinned SHA). They must be two separate Empire modules: `findmodule.yaml` and
`findprochandle.yaml`. Both close issue #1442.

Three further Outflank tools were considered and **rejected as duplicates** of
shipped capability: Kerberoast (#1435, already shipped in two forms), WdToggle
(#1437, `powershell/management/wdigest_downgrade.yaml`), ProcessListing (#1443, BOF
`bof/situational_awareness/tasklist.yaml`). domaininfo and lapsdump have partial
overlaps but provide a distinct in-process/BOF surface that avoids the
PowerShell/AMSI layer their PS equivalents trip.

## Build pipeline

All steps are grounded in the empirically verified state of the repo at the pinned
SHA, compiled and confirmed on this machine before writing this spec.

1. **Clone + pin.** Clone `outflanknl/C2-Tool-Collection` to a temp dir at
   `e371a38c717edaf1650923575ab33bee0dd3e0ee` (the SHA all modules cite). Build is
   fully reproducible from this SHA.

2. **Compile flags.** All six Outflank BOFs use an identical Makefile pattern
   (verified). The canonical compile commands per arch are:
   ```
   x64: x86_64-w64-mingw32-gcc -masm=intel -o <tool>.x64.o -c <src>.c
        x86_64-w64-mingw32-strip --strip-unneeded <tool>.x64.o
   x86: i686-w64-mingw32-gcc   -masm=intel -DWOW64 -fno-leading-underscore -o <tool>.x86.o -c <src>.c
        i686-w64-mingw32-strip  --strip-unneeded <tool>.x86.o
   ```
   Run `make` from each tool's `SOURCE/` directory — this is equivalent to the above
   and keeps the Makefile as the single source of truth. All six tools (and both
   source files of FindObjects) compiled cleanly with zero errors or warnings at the
   pinned SHA on this machine.

3. **No companion objects required.** Existing Empire BOF modules vendor exactly one
   `.o` per arch and no companion `beacon_funcs.o`/`beacon_generate.o`. Empire's
   loader supplies beacon APIs at runtime via the `Architecture`-selected
   `beacon_funcs.o` that Empire itself controls. Outflank's BOFs follow the same
   beacon stub pattern (confirmed by examining their `#include "beacon.h"` pattern).
   Do not vendor any additional objects alongside the BOF `.o` files.

4. **Vendor objects.** After compilation, rename and place:
   - `<ToolName>.x64.o` → `empire/server/data/module_source/bof/<category>/<module>/<module>.x64.o`
   - `<ToolName>.x86.o` → `empire/server/data/module_source/bof/<category>/<module>/<module>.x86.o`

   The output name from the upstream Makefile uses PascalCase (e.g. `ReconAD.x64.o`);
   rename to the lowercase Empire module name on copy (e.g. `reconad.x64.o`). For
   FindObjects: `FindModule.x64.o` → `findmodule/findmodule.x64.o`, and
   `FindProcHandle.x64.o` → `findprochandle/findprochandle.x64.o`.

5. **Write YAMLs.** One commit per module; seven commits total on the feature branch.

## Argument packing (format_string)

Format strings are **empirically derived** from each BOF's `go()` function at the
pinned SHA, not inferred. The unpack calls and resulting format chars:

| Module | Unpack sequence | `format_string` |
|--------|----------------|-----------------|
| reconad | Extract(W), Extract(W), Extract(W), Int, Int, Extract(W) | `ZZZiiZ` | Options in order: `Objects (Z)`, `Filter (Z)`, `Attributes (Z)`, `MaxResults (i)`, `UseGC (i)`, `Server (Z)` |
| domaininfo | none | `''` |
| smbinfo | Extract(W) | `Z` |
| findmodule | Extract(W) | `Z` |
| findprochandle | Extract(W) | `Z` |
| startwebclient | none (receives Args/Length, never calls BeaconDataParse) | `''` |
| lapsdump | Extract(W) | `Z` |

**Type-char conventions (constraints for YAML authors):**

- `Z` — `BeaconDataExtract` result cast to `WCHAR*`/`LPWSTR`. Empire's packer
  encodes as UTF-16LE; the BOF reads those bytes as wide string.
- `z` — `BeaconDataExtract` consumed as `char*` (ANSI). Do **not** use `z` where the
  BOF casts to `LPWSTR` — it silently corrupts every string argument.
- `i` — `BeaconDataInt` (int32). Use `i` for all integer-typed BOF args, including
  enums/flags, to match the convention of every existing Empire BOF (e.g. `ldapsearch
  zziizzi`, `reg_query zizzi`). Only use `s` (`BeaconDataShort`) when the upstream
  `go()` explicitly calls `BeaconDataShort` and the value range is ≤ 0xFFFF unsigned.
- **No `depends_on` on BOF-argument options.** Empire's `validate_options` includes
  options with an unmet `depends_on` in the arg list with their default values (it
  does not drop them). A `depends_on`-gated option would pass the static `len(format_string)
  == option_count` check but silently shift subsequent field positions at runtime,
  reintroducing the agent-crash class the check is designed to prevent.

## Per-module YAML structure

Modeled exactly on the existing TrustedSec BOF YAMLs. Fields:

- `name`: lowercase module name matching the vendored `.o` filename stem.
- `authors`: credit Outflank (handle + `https://github.com/outflanknl`) and the
  original tool author where the source names one.
- `description`: what the BOF does, its arguments, and a one-line opsec note.
- `software: ''`, `tactics: [...]`, `techniques: [...]`: from each issue's ATT&CK
  mapping.
- `background: false`, `needs_admin`, `opsec_safe`: per tool.
- `language: bof`.
- `comments:` — upstream repo URL **and** pinned SHA `e371a38c717edaf1650923575ab33bee0dd3e0ee`.
- `options:` — `Architecture` first (x64/x86, `strict: true`), then one option per
  BOF argument in `format_string` order. No `depends_on` on any BOF-argument option
  (see above). Integer/enum args use `strict: true` + `suggested_values`.
- `bof:` — `x86`/`x64` object paths, `entry_point: ''`, `format_string: <from table above>`.
- `script_path: ''`, `script_end: ''`.
- A sibling `<module>.py` with `custom_generate` is added **only** if a tool needs
  custom argument assembly or output formatting — most of these tools won't (all
  format strings are simple; none has the `ZZZZ` + custom-routing complexity of
  `wmi_query`). Default: no sibling `.py`.

## Testing & verification

**In-environment (automated, must pass before PR opens):**

- Each vendored `.o` is a valid COFF object for the declared architecture:
  `file *.x64.o` → "x86-64 COFF", `file *.x86.o` → "80386 COFF".
- For every module: `len(format_string) == count of non-Architecture options`. This
  is a static assertion, not sufficient on its own (see below).
- Extend the module-loading test in `empire/test/` to cover the seven new modules.
  The test must exercise the BOF generate path (call `process_arguments` /
  `bof_pack` with default params), not only YAML load/register — this is the layer
  where an arg-count or type mismatch surfaces (cf. `bof_packer.py` length check),
  which is the stated #1 risk for this bundle.
- `ruff check .` / `ruff format .` / yamlfmt clean, repo-wide.

**Not verifiable here (deferred to project owner with live Windows beacon):**

- Real BOF execution against a target. Each issue's "Smoke test" acceptance checkbox
  stays **unchecked** in the PR; the PR body lists what still needs live validation.

## Branch / PR

- Branch `feat/outflank-bof-bundle` off `7.0-dev` (already created).
- One PR closing #1433, #1434, #1438, #1439, #1440, #1442; body notes:
  - #1441 deferred to a future C# bundle.
  - Link to the written Outflank permission artifact (**required before merge**).
  - List of pending live smoke-tests per module.
- Seven commits, one per module, for reviewability.

## Rejected alternatives

- **Vendor prebuilt `.o` from upstream releases** — Outflank distributes source, not
  compiled objects; shipping opaque third-party binaries is neither reproducible nor
  auditable.
- **Partial-link FindObjects into one object** — fails: both source files define
  duplicate `go()` and shared helpers. Confirmed empirically with `ld -r`.
- **Runtime-fetch installer (#1470 pattern)** — the project owner chose in-tree
  vendoring; the opt-in fetch installer is the GPL-governance track and is reserved
  as a fallback if written Outflank permission cannot be obtained.
- **Include the three duplicate tools** (Kerberoast/WdToggle/ProcessListing) —
  rejected; shipped capability already covers them.

## Adversarial review waivers

*(none)*

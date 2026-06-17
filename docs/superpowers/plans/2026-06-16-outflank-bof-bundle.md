# Outflank BOF Bundle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add seven BOF modules from Outflank's C2-Tool-Collection (reconad, domaininfo, smbinfo, findmodule, findprochandle, startwebclient, lapsdump) to Empire's in-tree BOF module set as compiled COFF objects with YAML descriptors.

**Architecture:** Each module follows the existing TrustedSec-BOF pattern: a YAML under `empire/server/modules/bof/<category>/` pointing to `<tool>.x64.o` and `<tool>.x86.o` vendored under `empire/server/data/module_source/bof/<category>/<tool>/`. `generate_script_bof` in `module_service.py` reads the object, packs arguments via `bof_packer.process_arguments` using the YAML's `format_string`, and dispatches to RunCOFF. No Python or C# code changes are required — only new YAML files, new vendored objects, and new tests.

**Tech Stack:** mingw-w64 cross-compiler (already installed), `make`, YAML, pytest, `empire.server.utils.bof_packer.process_arguments`

## Global Constraints

- Pinned upstream SHA: `e371a38c717edaf1650923575ab33bee0dd3e0ee` (`outflanknl/C2-Tool-Collection`)
- Build flags: x64 — `x86_64-w64-mingw32-gcc -masm=intel -o <tool>.x64.o -c <src>.c && x86_64-w64-mingw32-strip --strip-unneeded <tool>.x64.o`; x86 — `i686-w64-mingw32-gcc -masm=intel -DWOW64 -fno-leading-underscore -o <tool>.x86.o -c <src>.c && i686-w64-mingw32-strip --strip-unneeded <tool>.x86.o`. Or equivalently: `cd BOF/<Tool>/SOURCE && make`.
- Object naming convention: lowercase Empire module name, e.g. `ReconAD.x64.o` → `reconad.x64.o`
- No `depends_on` on any BOF-argument option (causes silent arg-position shifts at runtime)
- All string args that the BOF casts to `WCHAR*`/`LPWSTR` use format char `Z`; ANSI `char*` use `z`; int32 use `i`
- Integer/enum options must use `strict: true` + `suggested_values`
- `comments:` field must cite upstream URL + SHA `e371a38c717edaf1650923575ab33bee0dd3e0ee`
- PR must link a written Outflank permission artifact before merge (see spec §License gate)
- Branch: `feat/outflank-bof-bundle` (already exists off `7.0-dev`)
- Tests in: `empire/test/test_module_service.py`
- Ruff + yamlfmt must pass repo-wide before opening PR
- `./ps-empire test` must not regress

---

## Task 0: Clone, build, and verify all seven BOF objects

**Files:**
- Create: `empire/server/data/module_source/bof/lateral_movement/startwebclient/` (dir only)
- Create: `empire/server/data/module_source/bof/situational_awareness/domaininfo/` (dir only)
- Create: `empire/server/data/module_source/bof/situational_awareness/smbinfo/` (dir only)
- Create: `empire/server/data/module_source/bof/situational_awareness/findmodule/` (dir only)
- Create: `empire/server/data/module_source/bof/situational_awareness/findprochandle/` (dir only)
- Create: `empire/server/data/module_source/bof/situational_awareness/reconad/` (dir only)
- Create: `empire/server/data/module_source/bof/credentials/lapsdump/` (dir only)

**Interfaces:**
- Produces: vendored `.x64.o` and `.x86.o` for all seven modules at the paths referenced in Tasks 1-7

- [ ] **Step 1: Clone the upstream repo at the pinned SHA**

```bash
cd /tmp
git clone https://github.com/outflanknl/C2-Tool-Collection.git c2tc
cd c2tc
git checkout e371a38c717edaf1650923575ab33bee0dd3e0ee
```

Expected: clean checkout. `git rev-parse HEAD` → `e371a38c717edaf1650923575ab33bee0dd3e0ee`

- [ ] **Step 2: Build all six upstream BOF source directories**

Run `make` from each tool's `SOURCE/` directory (the Makefile handles both arches):

```bash
cd /tmp/c2tc
for t in StartWebClient Domaininfo Smbinfo FindObjects Lapsdump ReconAD; do
  (cd BOF/$t/SOURCE && make) || echo "FAIL: $t"
done
```

Expected: no failures. FindObjects produces four objects (two `.c` files, each dual-arch): `FindModule.x64.o`, `FindModule.x86.o`, `FindProcHandle.x64.o`, `FindProcHandle.x86.o`. All others produce two.

- [ ] **Step 3: Verify COFF type for every output object**

```bash
cd /tmp/c2tc
file BOF/StartWebClient/StartWebClient.x64.o
file BOF/StartWebClient/StartWebClient.x86.o
file BOF/Domaininfo/Domaininfo.x64.o
file BOF/Domaininfo/Domaininfo.x86.o
file BOF/Smbinfo/Smbinfo.x64.o
file BOF/Smbinfo/Smbinfo.x86.o
file BOF/FindObjects/FindModule.x64.o
file BOF/FindObjects/FindModule.x86.o
file BOF/FindObjects/FindProcHandle.x64.o
file BOF/FindObjects/FindProcHandle.x86.o
file BOF/Lapsdump/Lapsdump.x64.o
file BOF/Lapsdump/Lapsdump.x86.o
file BOF/ReconAD/ReconAD.x64.o
file BOF/ReconAD/ReconAD.x86.o
```

Expected: each `.x64.o` → `x86-64 COFF object`. Each `.x86.o` → `80386 COFF object`.

- [ ] **Step 4: Create vendor directories**

```bash
cd /home/kali/Empire-Sponsors
mkdir -p empire/server/data/module_source/bof/lateral_movement/startwebclient
mkdir -p empire/server/data/module_source/bof/situational_awareness/domaininfo
mkdir -p empire/server/data/module_source/bof/situational_awareness/smbinfo
mkdir -p empire/server/data/module_source/bof/situational_awareness/findmodule
mkdir -p empire/server/data/module_source/bof/situational_awareness/findprochandle
mkdir -p empire/server/data/module_source/bof/situational_awareness/reconad
mkdir -p empire/server/data/module_source/bof/credentials/lapsdump
```

---

## Task 1: startwebclient — arg-less lateral-movement BOF

**Files:**
- Create: `empire/server/data/module_source/bof/lateral_movement/startwebclient/startwebclient.x64.o`
- Create: `empire/server/data/module_source/bof/lateral_movement/startwebclient/startwebclient.x86.o`
- Create: `empire/server/modules/bof/lateral_movement/startwebclient.yaml`
- Modify: `empire/test/test_module_service.py`

**Interfaces:**
- Consumes: vendored objects from Task 0, `module_service` fixture in `test_module_service.py`
- Produces: module ID `bof_lateral_movement_startwebclient`, accessible via `module_service.execute_module`

- [ ] **Step 1: Write the failing test**

Open `empire/test/test_module_service.py`. Add this function at the end of the file (before any `if __name__` block, if present):

```python
def test_execute_module_bof_startwebclient(module_service, agent_mock):
    """StartWebClient BOF: arg-less lateral_movement module triggers WebClient service."""
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Architecture": "x64",
    }
    module_id = "bof_lateral_movement_startwebclient"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )
    assert err is None
    assert res.command == "TASK_CSHARP_CMD_WAIT"
```

- [ ] **Step 2: Run the test — expect FAIL**

```bash
cd /home/kali/Empire-Sponsors
./ps-empire test empire/test/test_module_service.py::test_execute_module_bof_startwebclient -v
```

Expected: FAIL — `AssertionError` because `err == "Module not found for id bof_lateral_movement_startwebclient"` and `res is None`.

- [ ] **Step 3: Vendor the compiled objects**

```bash
cp /tmp/c2tc/BOF/StartWebClient/StartWebClient.x64.o \
   empire/server/data/module_source/bof/lateral_movement/startwebclient/startwebclient.x64.o
cp /tmp/c2tc/BOF/StartWebClient/StartWebClient.x86.o \
   empire/server/data/module_source/bof/lateral_movement/startwebclient/startwebclient.x86.o
```

- [ ] **Step 4: Write the YAML**

Create `empire/server/modules/bof/lateral_movement/startwebclient.yaml`:

```yaml
name: startwebclient
authors:
  - name: Cornelis de Plaa
    handle: '@Cneelis'
    link: https://github.com/outflanknl/C2-Tool-Collection
  - name: BC Security
description: |
  Beacon Object File (BOF) that starts the WebClient service on the local system by
  registering an ETW event for the MS-Windows-WebClntLookupServiceTrigger provider.
  Requires no service restart or direct SCM manipulation. Useful for enabling
  WebDAV-based NTLM coercion attacks (PetitPotam, PrinterBug) on systems where
  the WebClient service is stopped. Triggers a one-time event write and unregisters
  immediately.
software: ''
tactics: [TA0008]
techniques: [T1187]
background: false
output_extension:
needs_admin: false
opsec_safe: false
language: bof
min_language_version: ''
comments:
  - https://github.com/outflanknl/C2-Tool-Collection
  - 'Pinned SHA: e371a38c717edaf1650923575ab33bee0dd3e0ee'
options:
  - name: Architecture
    description: Architecture of the beacon_funcs.o to generate with (x64 or x86).
    required: true
    value: x64
    strict: true
    suggested_values:
      - x64
      - x86
bof:
  x86: bof/lateral_movement/startwebclient/startwebclient.x86.o
  x64: bof/lateral_movement/startwebclient/startwebclient.x64.o
  entry_point: ''
  format_string: ''
script_path: ''
script_end: ''
```

- [ ] **Step 5: Run the test — expect PASS**

```bash
./ps-empire test empire/test/test_module_service.py::test_execute_module_bof_startwebclient -v
```

Expected: PASS.

- [ ] **Step 6: Lint**

```bash
poetry run ruff check empire/test/test_module_service.py --fix
poetry run ruff format empire/test/test_module_service.py
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add empire/server/data/module_source/bof/lateral_movement/startwebclient/
git add empire/server/modules/bof/lateral_movement/startwebclient.yaml
git add empire/test/test_module_service.py
git commit -m "feat(bof): add Outflank startwebclient BOF module (#1434)

Starts the WebClient service via ETW event registration without direct
SCM manipulation. Enables WebDAV-based NTLM coercion on targets where
WebClient is stopped.

Source: outflanknl/C2-Tool-Collection @ e371a38c717edaf1650923575ab33bee0dd3e0ee"
```

---

## Task 2: domaininfo — arg-less situational_awareness BOF

**Files:**
- Create: `empire/server/data/module_source/bof/situational_awareness/domaininfo/domaininfo.x64.o`
- Create: `empire/server/data/module_source/bof/situational_awareness/domaininfo/domaininfo.x86.o`
- Create: `empire/server/modules/bof/situational_awareness/domaininfo.yaml`
- Modify: `empire/test/test_module_service.py`

**Interfaces:**
- Consumes: vendored objects from Task 0
- Produces: module ID `bof_situational_awareness_domaininfo`

- [ ] **Step 1: Write the failing test**

Append to `empire/test/test_module_service.py`:

```python
def test_execute_module_bof_domaininfo(module_service, agent_mock):
    """Domaininfo BOF: arg-less situational_awareness module enumerates domain membership."""
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Architecture": "x64",
    }
    module_id = "bof_situational_awareness_domaininfo"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )
    assert err is None
    assert res.command == "TASK_CSHARP_CMD_WAIT"
```

- [ ] **Step 2: Run the test — expect FAIL**

```bash
./ps-empire test empire/test/test_module_service.py::test_execute_module_bof_domaininfo -v
```

Expected: FAIL — `err == "Module not found for id bof_situational_awareness_domaininfo"`.

- [ ] **Step 3: Vendor the compiled objects**

```bash
cp /tmp/c2tc/BOF/Domaininfo/Domaininfo.x64.o \
   empire/server/data/module_source/bof/situational_awareness/domaininfo/domaininfo.x64.o
cp /tmp/c2tc/BOF/Domaininfo/Domaininfo.x86.o \
   empire/server/data/module_source/bof/situational_awareness/domaininfo/domaininfo.x86.o
```

- [ ] **Step 4: Write the YAML**

Create `empire/server/modules/bof/situational_awareness/domaininfo.yaml`:

```yaml
name: domaininfo
authors:
  - name: Cornelis de Plaa
    handle: '@Cneelis'
    link: https://github.com/outflanknl/C2-Tool-Collection
  - name: BC Security
description: |
  Beacon Object File (BOF) that enumerates Active Directory domain membership and
  Azure AD join status of the current host. Displays domain controller name, domain
  name, and site via NetGetDCName/DsGetSiteName; on Windows 10/2016+ also reports
  Azure AD tenant display name, tenant ID, device ID, and join type via
  NetGetAadJoinInformation. Operates via NetAPI32 and GetProcAddress only; no
  network-visible LDAP queries. Partial overlap with PowerView get_domain_* modules;
  this BOF variant avoids the PowerShell/AMSI surface and runs in-process.
software: ''
tactics: [TA0007]
techniques: [T1082]
background: false
output_extension:
needs_admin: false
opsec_safe: true
language: bof
min_language_version: ''
comments:
  - https://github.com/outflanknl/C2-Tool-Collection
  - 'Pinned SHA: e371a38c717edaf1650923575ab33bee0dd3e0ee'
options:
  - name: Architecture
    description: Architecture of the beacon_funcs.o to generate with (x64 or x86).
    required: true
    value: x64
    strict: true
    suggested_values:
      - x64
      - x86
bof:
  x86: bof/situational_awareness/domaininfo/domaininfo.x86.o
  x64: bof/situational_awareness/domaininfo/domaininfo.x64.o
  entry_point: ''
  format_string: ''
script_path: ''
script_end: ''
```

- [ ] **Step 5: Run the test — expect PASS**

```bash
./ps-empire test empire/test/test_module_service.py::test_execute_module_bof_domaininfo -v
```

Expected: PASS.

- [ ] **Step 6: Lint**

```bash
poetry run ruff check empire/test/test_module_service.py --fix
poetry run ruff format empire/test/test_module_service.py
```

- [ ] **Step 7: Commit**

```bash
git add empire/server/data/module_source/bof/situational_awareness/domaininfo/
git add empire/server/modules/bof/situational_awareness/domaininfo.yaml
git add empire/test/test_module_service.py
git commit -m "feat(bof): add Outflank domaininfo BOF module (#1439)

Enumerates AD domain membership and Azure AD join status via NetAPI32
in-process, avoiding the PowerShell/AMSI surface of PowerView equivalents.

Source: outflanknl/C2-Tool-Collection @ e371a38c717edaf1650923575ab33bee0dd3e0ee"
```

---

## Task 3: smbinfo — single wide-string arg BOF

**Files:**
- Create: `empire/server/data/module_source/bof/situational_awareness/smbinfo/smbinfo.x64.o`
- Create: `empire/server/data/module_source/bof/situational_awareness/smbinfo/smbinfo.x86.o`
- Create: `empire/server/modules/bof/situational_awareness/smbinfo.yaml`
- Modify: `empire/test/test_module_service.py`

**Interfaces:**
- Consumes: vendored objects from Task 0
- Produces: module ID `bof_situational_awareness_smbinfo`, `format_string: 'Z'`, option `Computername`

- [ ] **Step 1: Write the failing test**

Append to `empire/test/test_module_service.py`:

```python
def test_execute_module_bof_smbinfo(module_service, agent_mock):
    """Smbinfo BOF: single-arg situational_awareness module queries SMB host info."""
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Architecture": "x64",
        "Computername": ".",
    }
    module_id = "bof_situational_awareness_smbinfo"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )
    assert err is None
    assert res.command == "TASK_CSHARP_CMD_WAIT"
```

- [ ] **Step 2: Run the test — expect FAIL**

```bash
./ps-empire test empire/test/test_module_service.py::test_execute_module_bof_smbinfo -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Vendor the compiled objects**

```bash
cp /tmp/c2tc/BOF/Smbinfo/Smbinfo.x64.o \
   empire/server/data/module_source/bof/situational_awareness/smbinfo/smbinfo.x64.o
cp /tmp/c2tc/BOF/Smbinfo/Smbinfo.x86.o \
   empire/server/data/module_source/bof/situational_awareness/smbinfo/smbinfo.x86.o
```

- [ ] **Step 4: Write the YAML**

Create `empire/server/modules/bof/situational_awareness/smbinfo.yaml`:

```yaml
name: smbinfo
authors:
  - name: Cornelis de Plaa
    handle: '@Cneelis'
    link: https://github.com/outflanknl/C2-Tool-Collection
  - name: BC Security
description: |
  Beacon Object File (BOF) that retrieves SMB information from a target host via
  NetServerGetInfo, including server name, operating system version, platform ID,
  and session statistics. Does not authenticate or enumerate shares; provides
  lightweight remote host fingerprinting using existing SMB connectivity.
software: ''
tactics: [TA0007]
techniques: [T1046]
background: false
output_extension:
needs_admin: false
opsec_safe: true
language: bof
min_language_version: ''
comments:
  - https://github.com/outflanknl/C2-Tool-Collection
  - 'Pinned SHA: e371a38c717edaf1650923575ab33bee0dd3e0ee'
options:
  - name: Architecture
    description: Architecture of the beacon_funcs.o to generate with (x64 or x86).
    required: true
    value: x64
    strict: true
    suggested_values:
      - x64
      - x86
  - name: Computername
    description: Target hostname or IP address to query SMB information from. Use
      '.' for the local machine.
    required: true
    value: '.'
bof:
  x86: bof/situational_awareness/smbinfo/smbinfo.x86.o
  x64: bof/situational_awareness/smbinfo/smbinfo.x64.o
  entry_point: ''
  format_string: 'Z'
script_path: ''
script_end: ''
```

- [ ] **Step 5: Run the test — expect PASS**

```bash
./ps-empire test empire/test/test_module_service.py::test_execute_module_bof_smbinfo -v
```

Expected: PASS.

- [ ] **Step 6: Lint**

```bash
poetry run ruff check empire/test/test_module_service.py --fix
poetry run ruff format empire/test/test_module_service.py
```

- [ ] **Step 7: Commit**

```bash
git add empire/server/data/module_source/bof/situational_awareness/smbinfo/
git add empire/server/modules/bof/situational_awareness/smbinfo.yaml
git add empire/test/test_module_service.py
git commit -m "feat(bof): add Outflank smbinfo BOF module (#1440)

Queries SMB server info (OS version, platform, session stats) from a
target host via NetServerGetInfo without enumerating shares.

Source: outflanknl/C2-Tool-Collection @ e371a38c717edaf1650923575ab33bee0dd3e0ee"
```

---

## Task 4: lapsdump — credentials BOF

**Files:**
- Create: `empire/server/data/module_source/bof/credentials/lapsdump/lapsdump.x64.o`
- Create: `empire/server/data/module_source/bof/credentials/lapsdump/lapsdump.x86.o`
- Create: `empire/server/modules/bof/credentials/lapsdump.yaml`
- Modify: `empire/test/test_module_service.py`

**Interfaces:**
- Consumes: vendored objects from Task 0
- Produces: module ID `bof_credentials_lapsdump`, `format_string: 'Z'`, option `Computername`

- [ ] **Step 1: Write the failing test**

Append to `empire/test/test_module_service.py`:

```python
def test_execute_module_bof_lapsdump(module_service, agent_mock):
    """Lapsdump BOF: credentials module reads LAPS passwords from AD via LDAP."""
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Architecture": "x64",
        "Computername": "*",
    }
    module_id = "bof_credentials_lapsdump"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )
    assert err is None
    assert res.command == "TASK_CSHARP_CMD_WAIT"
```

- [ ] **Step 2: Run the test — expect FAIL**

```bash
./ps-empire test empire/test/test_module_service.py::test_execute_module_bof_lapsdump -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Vendor the compiled objects**

```bash
cp /tmp/c2tc/BOF/Lapsdump/Lapsdump.x64.o \
   empire/server/data/module_source/bof/credentials/lapsdump/lapsdump.x64.o
cp /tmp/c2tc/BOF/Lapsdump/Lapsdump.x86.o \
   empire/server/data/module_source/bof/credentials/lapsdump/lapsdump.x86.o
```

- [ ] **Step 4: Write the YAML**

Create `empire/server/modules/bof/credentials/lapsdump.yaml`:

```yaml
name: lapsdump
authors:
  - name: Cornelis de Plaa
    handle: '@Cneelis'
    link: https://github.com/outflanknl/C2-Tool-Collection
  - name: BC Security
description: |
  Beacon Object File (BOF) that dumps LAPS (Local Administrator Password Solution)
  passwords from Active Directory by querying the ms-Mcs-AdmPwd attribute via LDAP
  using the current user context. Specify a computer name to retrieve a single
  target's password, or '*' to enumerate all computers in the domain. Requires read
  access to ms-Mcs-AdmPwd — typically Domain Admins or explicitly delegated accounts.
  BOF form avoids the PowerShell/AMSI surface of the existing get_lapspasswords module.
software: ''
tactics: [TA0006]
techniques: [T1555]
background: false
output_extension:
needs_admin: false
opsec_safe: true
language: bof
min_language_version: ''
comments:
  - https://github.com/outflanknl/C2-Tool-Collection
  - 'Pinned SHA: e371a38c717edaf1650923575ab33bee0dd3e0ee'
options:
  - name: Architecture
    description: Architecture of the beacon_funcs.o to generate with (x64 or x86).
    required: true
    value: x64
    strict: true
    suggested_values:
      - x64
      - x86
  - name: Computername
    description: Target computer name to retrieve the LAPS password for. Use '*'
      to enumerate all computers in the domain.
    required: true
    value: '*'
bof:
  x86: bof/credentials/lapsdump/lapsdump.x86.o
  x64: bof/credentials/lapsdump/lapsdump.x64.o
  entry_point: ''
  format_string: 'Z'
script_path: ''
script_end: ''
```

- [ ] **Step 5: Run the test — expect PASS**

```bash
./ps-empire test empire/test/test_module_service.py::test_execute_module_bof_lapsdump -v
```

Expected: PASS.

- [ ] **Step 6: Lint**

```bash
poetry run ruff check empire/test/test_module_service.py --fix
poetry run ruff format empire/test/test_module_service.py
```

- [ ] **Step 7: Commit**

```bash
git add empire/server/data/module_source/bof/credentials/lapsdump/
git add empire/server/modules/bof/credentials/lapsdump.yaml
git add empire/test/test_module_service.py
git commit -m "feat(bof): add Outflank lapsdump BOF module (#1433)

Dumps LAPS ms-Mcs-AdmPwd via LDAP in-process, avoiding the
PowerShell/AMSI surface of the existing get_lapspasswords module.

Source: outflanknl/C2-Tool-Collection @ e371a38c717edaf1650923575ab33bee0dd3e0ee"
```

---

## Task 5: findmodule — single wide-string arg situational_awareness BOF

**Files:**
- Create: `empire/server/data/module_source/bof/situational_awareness/findmodule/findmodule.x64.o`
- Create: `empire/server/data/module_source/bof/situational_awareness/findmodule/findmodule.x86.o`
- Create: `empire/server/modules/bof/situational_awareness/findmodule.yaml`
- Modify: `empire/test/test_module_service.py`

**Interfaces:**
- Consumes: `FindModule.x64.o` / `FindModule.x86.o` from Task 0 (from `BOF/FindObjects/`)
- Produces: module ID `bof_situational_awareness_findmodule`, `format_string: 'Z'`, option `ModuleName`

- [ ] **Step 1: Write the failing test**

Append to `empire/test/test_module_service.py`:

```python
def test_execute_module_bof_findmodule(module_service, agent_mock):
    """FindModule BOF: enumerates processes with a given DLL loaded."""
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Architecture": "x64",
        "ModuleName": "amsi.dll",
    }
    module_id = "bof_situational_awareness_findmodule"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )
    assert err is None
    assert res.command == "TASK_CSHARP_CMD_WAIT"
```

- [ ] **Step 2: Run the test — expect FAIL**

```bash
./ps-empire test empire/test/test_module_service.py::test_execute_module_bof_findmodule -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Vendor the compiled objects**

Note: the upstream source is `BOF/FindObjects/FindModule.c` — rename on copy to the Empire module name.

```bash
cp /tmp/c2tc/BOF/FindObjects/FindModule.x64.o \
   empire/server/data/module_source/bof/situational_awareness/findmodule/findmodule.x64.o
cp /tmp/c2tc/BOF/FindObjects/FindModule.x86.o \
   empire/server/data/module_source/bof/situational_awareness/findmodule/findmodule.x86.o
```

- [ ] **Step 4: Write the YAML**

Create `empire/server/modules/bof/situational_awareness/findmodule.yaml`:

```yaml
name: findmodule
authors:
  - name: Cornelis de Plaa
    handle: '@Cneelis'
    link: https://github.com/outflanknl/C2-Tool-Collection
  - name: BC Security
description: |
  Beacon Object File (BOF) that enumerates all running processes and reports which
  ones have a specified module (DLL) loaded. Enables SeDebugPrivilege to access all
  processes. Useful for identifying processes injected with implants or locating
  which processes have EDR/AV modules loaded. Note: partial overlap with existing
  findLoadedModule (TrustedSec, two-arg ANSI form); this Outflank variant takes a
  single wide-string module name without a secondary process-name filter.
  Compiled from FindModule.c in the Outflank FindObjects directory.
software: ''
tactics: [TA0007]
techniques: [T1057]
background: false
output_extension:
needs_admin: false
opsec_safe: true
language: bof
min_language_version: ''
comments:
  - https://github.com/outflanknl/C2-Tool-Collection
  - 'Pinned SHA: e371a38c717edaf1650923575ab33bee0dd3e0ee'
  - 'Source file: BOF/FindObjects/SOURCE/FindModule.c'
options:
  - name: Architecture
    description: Architecture of the beacon_funcs.o to generate with (x64 or x86).
    required: true
    value: x64
    strict: true
    suggested_values:
      - x64
      - x86
  - name: ModuleName
    description: Name of the DLL to search for across all running processes, e.g.
      amsi.dll.
    required: true
    value: ''
bof:
  x86: bof/situational_awareness/findmodule/findmodule.x86.o
  x64: bof/situational_awareness/findmodule/findmodule.x64.o
  entry_point: ''
  format_string: 'Z'
script_path: ''
script_end: ''
```

- [ ] **Step 5: Run the test — expect PASS**

```bash
./ps-empire test empire/test/test_module_service.py::test_execute_module_bof_findmodule -v
```

Expected: PASS.

- [ ] **Step 6: Lint**

```bash
poetry run ruff check empire/test/test_module_service.py --fix
poetry run ruff format empire/test/test_module_service.py
```

- [ ] **Step 7: Commit**

```bash
git add empire/server/data/module_source/bof/situational_awareness/findmodule/
git add empire/server/modules/bof/situational_awareness/findmodule.yaml
git add empire/test/test_module_service.py
git commit -m "feat(bof): add Outflank findmodule BOF module (#1442)

Enumerates processes with a specific DLL loaded (FindModule.c from
FindObjects dir). Distinct from findLoadedModule: single wide-string arg,
no process-name filter.

Source: outflanknl/C2-Tool-Collection @ e371a38c717edaf1650923575ab33bee0dd3e0ee"
```

---

## Task 6: findprochandle — handle enumeration BOF

**Files:**
- Create: `empire/server/data/module_source/bof/situational_awareness/findprochandle/findprochandle.x64.o`
- Create: `empire/server/data/module_source/bof/situational_awareness/findprochandle/findprochandle.x86.o`
- Create: `empire/server/modules/bof/situational_awareness/findprochandle.yaml`
- Modify: `empire/test/test_module_service.py`

**Interfaces:**
- Consumes: `FindProcHandle.x64.o` / `FindProcHandle.x86.o` from Task 0 (from `BOF/FindObjects/`)
- Produces: module ID `bof_situational_awareness_findprochandle`, `format_string: 'Z'`, option `HandleName`

- [ ] **Step 1: Write the failing test**

Append to `empire/test/test_module_service.py`:

```python
def test_execute_module_bof_findprochandle(module_service, agent_mock):
    """FindProcHandle BOF: finds which processes hold a handle to a named object."""
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Architecture": "x64",
        "HandleName": "lsass.exe",
    }
    module_id = "bof_situational_awareness_findprochandle"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )
    assert err is None
    assert res.command == "TASK_CSHARP_CMD_WAIT"
```

- [ ] **Step 2: Run the test — expect FAIL**

```bash
./ps-empire test empire/test/test_module_service.py::test_execute_module_bof_findprochandle -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Vendor the compiled objects**

Note: source is `BOF/FindObjects/FindProcHandle.c` — rename on copy.

```bash
cp /tmp/c2tc/BOF/FindObjects/FindProcHandle.x64.o \
   empire/server/data/module_source/bof/situational_awareness/findprochandle/findprochandle.x64.o
cp /tmp/c2tc/BOF/FindObjects/FindProcHandle.x86.o \
   empire/server/data/module_source/bof/situational_awareness/findprochandle/findprochandle.x86.o
```

- [ ] **Step 4: Write the YAML**

Create `empire/server/modules/bof/situational_awareness/findprochandle.yaml`:

```yaml
name: findprochandle
authors:
  - name: Cornelis de Plaa
    handle: '@Cneelis'
    link: https://github.com/outflanknl/C2-Tool-Collection
  - name: BC Security
description: |
  Beacon Object File (BOF) that enumerates system handles across all running
  processes to find which processes hold a handle to a named object (file, key,
  event, mutex, etc.). Enables SeDebugPrivilege to access all processes. Useful for
  identifying which process holds an exclusive lock on a file, or locating processes
  with handles open to specific protected resources such as lsass.exe.
  Compiled from FindProcHandle.c in the Outflank FindObjects directory.
software: ''
tactics: [TA0007]
techniques: [T1057]
background: false
output_extension:
needs_admin: false
opsec_safe: true
language: bof
min_language_version: ''
comments:
  - https://github.com/outflanknl/C2-Tool-Collection
  - 'Pinned SHA: e371a38c717edaf1650923575ab33bee0dd3e0ee'
  - 'Source file: BOF/FindObjects/SOURCE/FindProcHandle.c'
options:
  - name: Architecture
    description: Architecture of the beacon_funcs.o to generate with (x64 or x86).
    required: true
    value: x64
    strict: true
    suggested_values:
      - x64
      - x86
  - name: HandleName
    description: Name of the object to search for across all process handles, e.g.
      lsass.exe or \Device\HarddiskVolume1.
    required: true
    value: ''
bof:
  x86: bof/situational_awareness/findprochandle/findprochandle.x86.o
  x64: bof/situational_awareness/findprochandle/findprochandle.x64.o
  entry_point: ''
  format_string: 'Z'
script_path: ''
script_end: ''
```

- [ ] **Step 5: Run the test — expect PASS**

```bash
./ps-empire test empire/test/test_module_service.py::test_execute_module_bof_findprochandle -v
```

Expected: PASS.

- [ ] **Step 6: Lint**

```bash
poetry run ruff check empire/test/test_module_service.py --fix
poetry run ruff format empire/test/test_module_service.py
```

- [ ] **Step 7: Commit**

```bash
git add empire/server/data/module_source/bof/situational_awareness/findprochandle/
git add empire/server/modules/bof/situational_awareness/findprochandle.yaml
git add empire/test/test_module_service.py
git commit -m "feat(bof): add Outflank findprochandle BOF module (#1442)

Enumerates system handles across all processes to find which hold a
handle to a named object (FindProcHandle.c from FindObjects dir).

Source: outflanknl/C2-Tool-Collection @ e371a38c717edaf1650923575ab33bee0dd3e0ee"
```

---

## Task 7: reconad — six-argument ADSI AD enumeration BOF

**Files:**
- Create: `empire/server/data/module_source/bof/situational_awareness/reconad/reconad.x64.o`
- Create: `empire/server/data/module_source/bof/situational_awareness/reconad/reconad.x86.o`
- Create: `empire/server/modules/bof/situational_awareness/reconad.yaml`
- Modify: `empire/test/test_module_service.py`

**Interfaces:**
- Consumes: vendored objects from Task 0
- Produces: module ID `bof_situational_awareness_reconad`, `format_string: 'ZZZiiZ'`
- Option order (MUST match `go()` unpack sequence exactly): `Objects (Z)`, `Filter (Z)`, `Attributes (Z)`, `MaxResults (i)`, `UseGC (i)`, `Server (Z)`

- [ ] **Step 1: Write the failing test**

Append to `empire/test/test_module_service.py`:

```python
def test_execute_module_bof_reconad(module_service, agent_mock):
    """ReconAD BOF: six-arg ADSI AD enumeration; verifies ZZZiiZ format_string packing."""
    agent_mock.language = "csharp"
    params = {
        "Agent": agent_mock.session_id,
        "Architecture": "x64",
        "Objects": "users",
        "Filter": "*",
        "Attributes": "",
        "MaxResults": "100",
        "UseGC": "0",
        "Server": "",
    }
    module_id = "bof_situational_awareness_reconad"
    res, err = module_service.execute_module(
        None, agent_mock, module_id, params, True, True, None
    )
    assert err is None
    assert res.command == "TASK_CSHARP_CMD_WAIT"
```

- [ ] **Step 2: Run the test — expect FAIL**

```bash
./ps-empire test empire/test/test_module_service.py::test_execute_module_bof_reconad -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Vendor the compiled objects**

```bash
cp /tmp/c2tc/BOF/ReconAD/ReconAD.x64.o \
   empire/server/data/module_source/bof/situational_awareness/reconad/reconad.x64.o
cp /tmp/c2tc/BOF/ReconAD/ReconAD.x86.o \
   empire/server/data/module_source/bof/situational_awareness/reconad/reconad.x86.o
```

- [ ] **Step 4: Write the YAML**

The options list **must** be in this exact order to match the `go()` unpack sequence:
`Objects → Filter → Attributes → MaxResults → UseGC → Server`.

Create `empire/server/modules/bof/situational_awareness/reconad.yaml`:

```yaml
name: reconad
authors:
  - name: Cornelis de Plaa
    handle: '@Cneelis'
    link: https://github.com/outflanknl/C2-Tool-Collection
  - name: BC Security
description: |
  Beacon Object File (BOF) that performs ADSI-based Active Directory reconnaissance
  from within the beacon using LDAP or the Global Catalog. Set Objects to 'users',
  'groups', or 'computers' to target a specific class, or leave blank to query all
  types. Filter narrows by sAMAccountName (use '*' for all). Attributes is a
  comma-separated list of LDAP attributes to return; leave blank for defaults.
  MaxResults limits output (0 = no limit). Set UseGC to 1 to query the Global
  Catalog on port 3268 for cross-domain enumeration. Server pins the query to a
  specific domain controller; leave blank to auto-resolve.
software: ''
tactics: [TA0007]
techniques: [T1087.002]
background: false
output_extension:
needs_admin: false
opsec_safe: true
language: bof
min_language_version: ''
comments:
  - https://github.com/outflanknl/C2-Tool-Collection
  - 'Pinned SHA: e371a38c717edaf1650923575ab33bee0dd3e0ee'
options:
  - name: Architecture
    description: Architecture of the beacon_funcs.o to generate with (x64 or x86).
    required: true
    value: x64
    strict: true
    suggested_values:
      - x64
      - x86
  - name: Objects
    description: Object type to enumerate. One of 'users', 'groups', 'computers',
      or blank to query all types.
    required: false
    value: 'users'
  - name: Filter
    description: Filter value matched against sAMAccountName. Use '*' for all objects
      of the specified type.
    required: false
    value: '*'
  - name: Attributes
    description: Comma-separated list of LDAP attributes to return. Leave blank for
      the default attribute set for the selected object type.
    required: false
    value: ''
  - name: MaxResults
    description: Maximum number of results to return. Set to 0 to return all results.
    required: true
    value: '100'
  - name: UseGC
    description: Query the Global Catalog on port 3268 for cross-domain enumeration
      (1), or use standard LDAP (0).
    required: true
    value: '0'
    strict: true
    suggested_values:
      - '0'
      - '1'
  - name: Server
    description: Domain controller or LDAP server to query. Leave blank to
      auto-resolve from the current domain context.
    required: false
    value: ''
bof:
  x86: bof/situational_awareness/reconad/reconad.x86.o
  x64: bof/situational_awareness/reconad/reconad.x64.o
  entry_point: ''
  format_string: 'ZZZiiZ'
script_path: ''
script_end: ''
```

- [ ] **Step 5: Run the test — expect PASS**

```bash
./ps-empire test empire/test/test_module_service.py::test_execute_module_bof_reconad -v
```

Expected: PASS.

- [ ] **Step 6: Lint**

```bash
poetry run ruff check empire/test/test_module_service.py --fix
poetry run ruff format empire/test/test_module_service.py
```

- [ ] **Step 7: Commit**

```bash
git add empire/server/data/module_source/bof/situational_awareness/reconad/
git add empire/server/modules/bof/situational_awareness/reconad.yaml
git add empire/test/test_module_service.py
git commit -m "feat(bof): add Outflank reconad BOF module (#1438)

ADSI-based AD recon (users/groups/computers) via LDAP or Global Catalog
in-process. Six-arg format string ZZZiiZ; option order matches go()
unpack sequence exactly to prevent silent arg-position corruption.

Source: outflanknl/C2-Tool-Collection @ e371a38c717edaf1650923575ab33bee0dd3e0ee"
```

---

## Task 8: Final validation and PR prep

**Files:**
- No new files

**Interfaces:**
- Consumes: all seven modules from Tasks 1-7

- [ ] **Step 1: Run the full module test suite**

```bash
./ps-empire test empire/test/test_module_service.py -v
```

Expected: all existing tests still pass; seven new tests pass.

- [ ] **Step 2: Run repo-wide ruff and yamlfmt**

```bash
poetry run ruff check . --fix
poetry run ruff format .
pre-commit run yamlfmt --all-files 2>/dev/null || true
```

If ruff or yamlfmt make changes, stage and amend the affected module's last commit, or add a cleanup commit:

```bash
git add -p   # stage only the lint-fix changes
git commit -m "chore: ruff/yamlfmt cleanup for Outflank BOF bundle"
```

- [ ] **Step 3: Verify all seven .o files are valid COFF**

```bash
for f in \
  empire/server/data/module_source/bof/lateral_movement/startwebclient/startwebclient.x64.o \
  empire/server/data/module_source/bof/lateral_movement/startwebclient/startwebclient.x86.o \
  empire/server/data/module_source/bof/situational_awareness/domaininfo/domaininfo.x64.o \
  empire/server/data/module_source/bof/situational_awareness/domaininfo/domaininfo.x86.o \
  empire/server/data/module_source/bof/situational_awareness/smbinfo/smbinfo.x64.o \
  empire/server/data/module_source/bof/situational_awareness/smbinfo/smbinfo.x86.o \
  empire/server/data/module_source/bof/situational_awareness/findmodule/findmodule.x64.o \
  empire/server/data/module_source/bof/situational_awareness/findmodule/findmodule.x86.o \
  empire/server/data/module_source/bof/situational_awareness/findprochandle/findprochandle.x64.o \
  empire/server/data/module_source/bof/situational_awareness/findprochandle/findprochandle.x86.o \
  empire/server/data/module_source/bof/situational_awareness/reconad/reconad.x64.o \
  empire/server/data/module_source/bof/situational_awareness/reconad/reconad.x86.o \
  empire/server/data/module_source/bof/credentials/lapsdump/lapsdump.x64.o \
  empire/server/data/module_source/bof/credentials/lapsdump/lapsdump.x86.o; do
  echo -n "$f: "; file "$f"
done
```

Expected: every `.x64.o` → `x86-64 COFF object`. Every `.x86.o` → `80386 COFF object`.

- [ ] **Step 4: Verify format_string / option-count invariant for all seven modules**

```bash
python3 - << 'EOF'
import yaml
from pathlib import Path

modules = [
    "empire/server/modules/bof/lateral_movement/startwebclient.yaml",
    "empire/server/modules/bof/situational_awareness/domaininfo.yaml",
    "empire/server/modules/bof/situational_awareness/smbinfo.yaml",
    "empire/server/modules/bof/situational_awareness/findmodule.yaml",
    "empire/server/modules/bof/situational_awareness/findprochandle.yaml",
    "empire/server/modules/bof/situational_awareness/reconad.yaml",
    "empire/server/modules/bof/credentials/lapsdump.yaml",
]
ok = True
for path in modules:
    doc = yaml.safe_load(Path(path).read_text())
    fmt = doc["bof"]["format_string"] or ""
    opts = [o for o in doc["options"] if o["name"].lower() != "architecture"]
    if len(fmt) != len(opts):
        print(f"FAIL {path}: format_string len={len(fmt)} but {len(opts)} non-Architecture options")
        ok = False
    else:
        print(f"OK   {path}: format_string='{fmt}' matches {len(opts)} option(s)")
if not ok:
    raise SystemExit(1)
EOF
```

Expected: all seven lines print `OK`.

- [ ] **Step 5: Open the PR**

```bash
gh pr create \
  --base 7.0-dev \
  --title "feat(bof): add 7 Outflank C2-Tool-Collection BOF modules" \
  --body "$(cat <<'EOF'
## Summary

Adds seven BOF modules from [outflanknl/C2-Tool-Collection](https://github.com/outflanknl/C2-Tool-Collection) @ `e371a38c717edaf1650923575ab33bee0dd3e0ee`:

| Module | Category | `format_string` | Closes |
|--------|----------|-----------------|--------|
| startwebclient | lateral_movement | `''` (arg-less) | #1434 |
| domaininfo | situational_awareness | `''` (arg-less) | #1439 |
| smbinfo | situational_awareness | `Z` | #1440 |
| lapsdump | credentials | `Z` | #1433 |
| findmodule | situational_awareness | `Z` | #1442 |
| findprochandle | situational_awareness | `Z` | #1442 |
| reconad | situational_awareness | `ZZZiiZ` | #1438 |

**Not in this PR:** #1441 RemotePipeList (`.NET / Roslyn` form factor, deferred to a future C# bundle).

## License

⚠️ **Required before merge:** Link the written Outflank permission artifact here.
_[Replace this line with a link to the email, upstream issue comment, or NOTICE entry confirming permission to vendor from outflanknl/C2-Tool-Collection.]_

## Pending live smoke-tests (need Windows beacon)

- [ ] startwebclient — verify WebClient service starts on target
- [ ] domaininfo — verify domain/Azure AD output on joined host
- [ ] smbinfo — verify SMB server info returned for a reachable host
- [ ] lapsdump — verify LAPS password retrieved (requires delegated read access)
- [ ] findmodule — verify amsi.dll listed in processes that load it
- [ ] findprochandle — verify handle search returns matching processes
- [ ] reconad — verify user/group/computer enumeration returns AD objects

## Test plan

- [x] `./ps-empire test empire/test/test_module_service.py` — all 7 new tests pass, no regressions
- [x] `file *.x64.o` → `x86-64 COFF`, `file *.x86.o` → `80386 COFF` for all 14 objects
- [x] format_string length == non-Architecture option count for all 7 modules
- [x] `ruff check . --fix` / `ruff format .` / yamlfmt clean repo-wide

🤖 Generated with [Claude Code](https://claude.ai/claude-code)
EOF
)"
```

---

## Self-review checklist

**Spec coverage:**
- ✅ All 7 modules specified in scope table implemented (Tasks 1-7)
- ✅ Pinned SHA cited in every YAML comments field
- ✅ Format strings match empirically-derived table from spec
- ✅ reconad option names in exact unpack order (Objects/Filter/Attributes/MaxResults/UseGC/Server)
- ✅ No `depends_on` on any BOF-argument option
- ✅ All string args that cast to LPWSTR use `Z`; integers use `i`
- ✅ Tests exercise `execute_module` → `generate_script_bof` → `process_arguments` path (bof_pack layer), not just YAML load
- ✅ format_string/option-count invariant verified programmatically in Task 8
- ✅ Ruff/yamlfmt repo-wide in Task 8
- ✅ PR body includes license gate notice and pending smoke-test checklist
- ✅ findmodule/findprochandle cite their upstream source file in comments (non-obvious rename)
- ✅ findmodule description notes overlap with existing findLoadedModule (TrustedSec)
- ✅ lapsdump and domaininfo descriptions note partial overlap with PS equivalents

# Credential Parsers

A credential parser turns raw agent task output into rows in Empire's credential store. Modules that harvest secrets — `mimikatz`, `Rubeus`, `SharpDPAPI`, `Invoke-Inveigh` — don't write to the database themselves. They declare a parser in their YAML, and Empire runs it against every batch of output the module returns.

Parsers live in `empire/server/common/credential_parsers/`, one module per parser.

## How ingestion works

`AgentCommunicationService._ingest_credentials` runs on every task-result batch, for both blocking (`TASK_*_CMD_WAIT`) and non-blocking job (`TASK_*_CMD_JOB`) output. Because it fires per batch rather than once at task completion, output streamed from a `background: true` module is ingested as it arrives.

Parser selection has two paths:

1. **Declared parser.** If the task came from a module, and that module's YAML sets `credential_parser`, that name is looked up in the registry.
2. **Prefix fallback.** If there's no module — an ad-hoc `shell` invocation — Empire sniffs the *first line only* of the output. A first line starting with `Hostname:` routes to `mimikatz`; one starting with `[+] Prompted credentials:` or containing `text returned:` routes to `prompt`. A match on any later line doesn't count.

If neither path yields a parser, the output is left alone.

## Writing a parser

A parser is any class satisfying the `CredentialParser` protocol in `base.py` — a single `parse` method:

```python
def parse(
    self, data: bytes | str, agent: "models.Agent | None"
) -> list[CredentialPostRequest]: ...
```

It's a `typing.Protocol`, so there's no base class to inherit from. Implement the method and you're done.

`data` arrives as either `bytes` or `str` depending on the agent language and response type. Normalise it with the `coerce_str` / `coerce_bytes` helpers from `base.py` rather than type-checking inline:

```python
from empire.server.common.credential_parsers.base import coerce_str

text = coerce_str(data)
```

Return an empty list when nothing matched. That's the normal case — the parser runs on every batch of a module's output, most of which carries no credentials.

A minimal parser, following the shape of the shipped ones:

```python
import re
from typing import TYPE_CHECKING

from empire.server.api.v2.credential.credential_dto import CredentialPostRequest
from empire.server.common.credential_parsers.base import coerce_str
from empire.server.common.credential_parsers.credtypes import PLAINTEXT

if TYPE_CHECKING:
    from empire.server.core.db import models

TOOL_TAG = "mytool"

_CRED_RE = re.compile(r"^(?P<domain>[^\\]*)\\(?P<user>[^:]+):(?P<password>.+)$")


class MyToolParser:
    """One-line summary of what output shape this handles."""

    def parse(
        self, data: bytes | str, agent: "models.Agent | None"
    ) -> list[CredentialPostRequest]:
        text = coerce_str(data)

        agent_host = getattr(agent, "hostname", "") or ""
        agent_os = getattr(agent, "os_details", None)

        results: list[CredentialPostRequest] = []
        seen: set[tuple[str, str]] = set()

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            match = _CRED_RE.match(line)
            if not match:
                continue

            username = match.group("user")
            password = match.group("password")

            key = (username.lower(), password)
            if key in seen:
                continue
            seen.add(key)

            results.append(
                CredentialPostRequest(
                    credtype=PLAINTEXT,
                    domain=match.group("domain"),
                    username=username,
                    password=password,
                    host=agent_host,
                    os=agent_os,
                    sid="",
                    notes=TOOL_TAG,
                )
            )

        return results
```

A few conventions worth following, all of which the shipped parsers observe:

**Deduplicate within the batch.** Tools that poll or run continuously re-emit the same capture. Keep a `seen` set keyed on whatever uniquely identifies a credential in that tool's output: parsers whose secret is a self-contained blob (`inveigh`, `kerberoast`, `rubeus`) key on the blob alone, while those emitting a bare secret per account (`internal_monologue`, `ntlmextract`, `pwdump_hashes`) key on a tuple like `(username.lower(), secret)`.

This dedup is **batch-scoped** — it collapses repeats within one task-result batch, and that's all it can do, since the parser is handed one batch at a time and holds no state between calls. Repeats spanning batches are caught downstream by the credential store's duplicate check. Don't try to compensate by keeping state on the parser instance: the registry holds one shared instance per parser, so anything you stash there leaks across agents and engagements.

**Fill `host` and `os` from the agent.** Most tool output doesn't carry the host it ran on. Use `getattr(agent, "hostname", "") or ""` and `getattr(agent, "os_details", None)` — `getattr` because `agent` may be `None`, and the `or ""` because `host` is a non-optional `str` on the DTO. If the output *does* carry a host of its own (`mimikatz` prints one), prefer that.

**Set `notes` to the tool tag only.** Don't add a timestamp; ingestion appends one for you (see below). If a row deserves extra qualification — a machine account, say — append a second tag: `f"{TOOL_TAG} {MACHINE_ACCOUNT_TAG}"`.

**Set `sid` to `""` when the tool doesn't report one.** The DTO field is optional but the column is more useful when it's consistently empty rather than sometimes `None`.

### The `agent=None` contract

`agent` is `None` only for ingestion paths that aren't tied to an Empire agent — a plugin tailing a third-party tool's log file, or a credential file upload. In that case leave `host` as `""` and `os` as `None` unless the input itself carries them.

The contract runs the other way too: **callers must pass the originating `Agent` whenever the data came from agent tasking.** Defaulting to `None` for convenience strips host attribution from credentials that have it. If you're writing a plugin that ingests credentials, import the parser directly, call `parse(data, None)`, and hand the results to `CredentialService.create_credential`.

## Choosing a credtype

`credtype` is a plain string column with no database enum behind it, so nothing stops you writing an arbitrary value — but parsers should reference the constants in `credtypes.py` rather than free-typing the literals:

```python
from empire.server.common.credential_parsers.credtypes import NETNTLMV2
```

The constants are `HASH`, `PLAINTEXT`, `NETNTLMV1`, `NETNTLMV2`, `DCC2`, `KRBTGS`, `KRBASREP`, `KRB_TICKET`, `KRB_SESSION_KEY`, `DPAPI_MASTERKEY`, `DPAPI_SYSTEM_KEY`, and `DPAPI_VAULT_CRED`. What the `password` column is expected to hold for each is documented in the `credtypes.py` docstring and in the [Credentials](../../starkiller/credentials.md#credential-types) reference table — check it before inventing a new type, since Starkiller and downstream tooling key off these values.

If your tool emits a secret shape that genuinely isn't covered, add a constant to `credtypes.py` with a comment describing the `password` format, and update the reference table.

## Registering the parser

Two steps.

First, add it to `_REGISTRY` in `empire/server/common/credential_parsers/__init__.py`:

```python
from empire.server.common.credential_parsers.mytool import MyToolParser

_REGISTRY: dict[str, CredentialParser] = {
    # ... existing parsers ...
    "mytool": MyToolParser(),
}
```

The registry holds instances, not classes — parsers are stateless singletons.

Then declare it in the module YAML:

```yaml
name: MyTool
description: ...
credential_parser: mytool
```

The `credential_parser` field is validated by `check_credential_parser` in `empire/server/core/module_models.py` when the module loads. An unrecognised name raises at startup with the list of registered parsers, so a YAML typo fails loudly instead of silently dropping credentials the first time the module runs.

Registering under a name no module declares is fine — `prompt` is registered but reached only through the prefix fallback.

## Error handling you get for free

Ingestion runs inside the agent comms loop, so it's written so that no single parser can break it. You don't need to defend against these yourself:

| Situation | What happens |
|---|---|
| Parser raises | Logged with traceback, batch skipped |
| Parser returns a non-list | Logged at error level, batch skipped |
| Module declares an unknown parser | Logged at error level, ingestion skipped for that module |
| Credential duplicates an existing row | Skipped **silently** — no log line |
| `create_credential` raises (DB error) | Logged, and the **remainder of the batch is aborted** |

Two of these are worth designing around. The silent duplicate skip means a module that only re-found credentials Empire already has is indistinguishable from one that found nothing — which is why in-parser dedup matters. And the DB-error case is the one failure that isn't scoped to a single row: later credentials in the same output are lost with it. `domain`, `username`, `password`, and `notes` are `Text` columns, but `credtype`, `os`, and `sid` are `String(255)` — so a parser that stuffs an unbounded value into one of those three can take the rest of the batch down with it.

Ingestion also stamps every row's `notes` with a timestamp on the way in, appending it to whatever the parser set. A row from the example above lands as `mytool 2026-08-21 19:36:34`.

## Testing

Parser tests live in `empire/test/test_credential_parsers.py`. Fixtures are kept **inline in the test** by deliberate convention rather than in a fixtures directory, so a regression shows up in diff review next to the parser change that caused it.

Only `hostname` and `os_details` are read off the agent, so a `SimpleNamespace` stands in for one:

```python
@pytest.fixture
def agent():
    return SimpleNamespace(hostname="WIN-AGENT", os_details="Windows 10 x64")
```

Cover at minimum: a representative capture producing the expected `credtype` / `domain` / `username` / `password`, unrelated output producing `[]`, and repeated identical captures collapsing to one row. If your regexes are shape-discriminated — as the Inveigh parser's NetNTLMv1 and v2 patterns are, by exact hex-segment length — assert that each shape doesn't match the other.

The registry test iterates `registered_parser_names()`, so a newly registered parser is picked up automatically:

```bash
pytest empire/test/test_credential_parsers.py
```

# Upgrading to 7.0

Empire 7.0 is a FIPS-hardening and cleanup release with breaking changes — the staging/comms crypto, password hashing, tags API, and base-directory layout all changed. Those changes invalidate most of what a pre-7.0 database holds: pre-7.0 agents can't talk to a 7.0 server, and pre-7.0 password hashes are unusable. **Move to 7.0 with a fresh database.**

Bring your checkout to 7.0 with `./ps-empire update` (see [Update](README.md#update)), then drop the old database:

```bash
./ps-empire server --reset
```

`--reset` drops the database and reinitializes the schema on the next start; it leaves `config.yaml`, certs, and downloads in place (see [Resetting](resetting.md)). `update` offers to apply pending migrations to the 6.x database on the way through — decline, since the reset discards it anyway.

Afterwards you'll recreate listeners and operator accounts and re-stage every agent. Re-staging is unavoidable regardless (see below), so there's little live state worth carrying across.

## Re-stage all agents

Nearly every crypto primitive in the staging/comms path changed for FIPS compliance:

* Staging key normalization: MD5 → SHA-256
* CSPRNG: `random`/`random.choice` → `secrets`/`SystemRandom`
* DH session key derivation: raw SHA-256 → HKDF-SHA256 (RFC 5869), normalized to a 768-byte shared secret
* Routing packet encryption: ChaCha20-Poly1305 → AES-256-GCM
* AES-CBC payload HMAC truncation: 10 bytes → 16 bytes

An agent staged before 7.0 cannot communicate with a 7.0 server — there is no compatibility shim. Re-stage everything after upgrading. See [Staging](../agents/staging.md) for the current process.

The C# agent (Sharpire) implements this crypto independently and needs its own update via the new Empire Compiler release (v2.0.0+); it isn't picked up automatically by `./ps-empire update`.

## Recreate operator accounts

Password hashing moved from bcrypt to PBKDF2-HMAC-SHA256 (FIPS SP 800-132), so pre-7.0 hashes are unusable. A fresh database starts with only the default `empireadmin` from `config.yaml` — recreate any other operator accounts via Starkiller or `POST /api/v2/users/`.

## `config.yaml` gets overwritten on every update

`./ps-empire update` overwrites the base `config.yaml` from the shipped template every run. Move any local customizations to `config.user.yaml` first — see [User Config Overrides](server.md#user-config-overrides).

## `SafeChecks` stager option removed

The per-stager `SafeChecks` option (PowerShell version guard, `Expect: 100-Continue`, macOS Little Snitch check) is gone. If you relied on its default-on behavior, opt in explicitly by adding `SafeChecksPS` and/or `SafeChecksPython` to a stager's `Bypasses`. See [Bypasses](../settings/bypasses.md).

## Tags are now a flat global registry

Per-entity `key:value` tags are gone. Tags are now unique names with a shared color/description, managed once via `/api/v2/tags` and attached/detached from entities by id. If you have automation or a custom frontend against the old tag API, it needs updating — see [Tags](../restful-api/README.md#tags). Starkiller 4.0 already speaks the new API.

## Removed in-agent shell aliases

The PowerShell, Python, and IronPython agents no longer intercept `shell` aliases like `ls`, `cd`, `pwd`, `ps`, `ipconfig`. `shell <cmd>` now always passes straight to the system shell. Use the `situational_awareness/host/*` modules for structured output and `TASK_CHDIR` (`POST /api/v2/agents/{id}/tasks/chdir`) to persistently change directory. See [Agents](../agents/README.md#shell-commands--working-directory).

## Removed modules

* `Seatbelt` — superseded by updated Empire Compiler modules.
* Legacy PowerShell BloodHound/SharpHound modules — replaced by the native C# `SharpHound` module.
* `powershell/management/switch_listener` and all switch-listener infrastructure.

## `StagerRetries` option removed

The unused `stager_retries` parameter and its corresponding `StagerRetries` stager option were removed from every listener and stager.

## Writing plugins or custom modules?

Plugin, listener, and stager developer-facing API changes (exceptions replacing tuple returns, `installPath` removal, etc.) are tracked separately in the [Plugin Migration Guide](../plugins/development/migration.md) (see its "6->7 Migration" section).

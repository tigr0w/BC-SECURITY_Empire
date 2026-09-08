# Port Forward Pivot

The Port Forward Pivot listener turns an active agent into a **userspace TCP relay**. It runs as a backgrounded job on the agent that forwards inbound connections on a chosen port to the Empire server, letting you chain agents through a host that can reach C2 when the target cannot.

Supported on PowerShell, C# (Sharpire), Go (Gopire), IronPython, and Linux/macOS Python agents.

## Key Configuration Options

### Agent

The active agent that will run the port-forward relay job.

### ListenPort

The port the agent listens on for inbound pivoted traffic (default 80).

### internalIP

The bind address on the agent host. Leave blank to use the agent's auto-detected internal IP.

## Privilege requirements

- **Windows agents must be elevated.** The listener pre-authorizes the inbound firewall rule via `netsh advfirewall` so the relay can bind silently; the rule is **removed automatically on shutdown**.
- **Linux/macOS Python agents** only need root to bind ports **below 1024**; higher ports run unprivileged.

## When to use

Use it to chain agents inward through a pivot host — the classic case is reaching a segmented subnet where only one compromised host can talk to your listener.

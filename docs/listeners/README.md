# Listeners

Listeners in Empire are responsible for handling agent connections. They serve as the communication channels between compromised hosts and the Empire server, relaying commands and responses. Listeners can operate over various transport mechanisms such as HTTP, HTTPS, and SMB.

Empire supports multiple listener types, providing flexibility in how agents communicate based on the environment and operational needs.

## Listener Tips

* **Host binding**: Ensure `Host` matches how your target can reach the server (public IP, domain, or redirector).
* **Ports**: Keep firewall rules in mind for both inbound and outbound traffic.

## Listener Types

Empire offers several listener types designed for different network conditions and evasion techniques:

* **HTTP/HTTPS**: A standard HTTP listener for internet-facing operations supports both standard HTTP and encrypted HTTPS.
* **HTTP Malleable**: A customizable HTTP listener that allows beacons to match specific threat profiles.
* **SMB**: A peer-to-peer listener that works over SMB pipes (**currently only supports IronPython**).
* **HTTP Hop**: A listener that adds an intermediate hop or redirection server using PHP.
* **Port Forward**: Enables chaining agents through port forwarding. Runs as a backgrounded userspace TCP relay job on the agent. Supported across PowerShell, C# (Sharpire), Go (Gopire), IronPython, and Linux/macOS Python agents. **Windows agents must be elevated** — the listener pre-authorizes the inbound firewall rule via `netsh advfirewall` so the relay can bind silently (rule is removed automatically on shutdown). Linux/macOS Python agents only need root for binding ports below 1024.
* **HTTP Foreign**: Allows one server to generate stagers and agents for another Empire server.

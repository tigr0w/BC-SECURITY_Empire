# SMB

The SMB listener is a **peer-to-peer** redirector that relays agent traffic over an **SMB named pipe** instead of an outbound HTTP channel. It is designed for internal pivoting: a host with no direct route to the Empire server can be reached by chaining its traffic through an existing agent that *can* reach the server.

> The SMB listener currently supports **IronPython agents only**.

## Key Configuration Options

Every option below is set when creating the listener in Starkiller.

### Agent

The existing agent that will host the SMB server. Traffic for the pivoted agent is relayed through this agent's connection back to Empire.

### PipeName

The name of the SMB named pipe the listener binds. Defaults to `empire_pipe`. Choose a pipe name that blends into the target environment to reduce detection.

## When to use

Reach for the SMB listener when a target host is firewalled off from direct C2 egress but can talk SMB to a host you already control. Pair it with the peer-to-peer staging flow so the pivoted agent negotiates through the hosting agent.

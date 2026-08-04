# HTTP Foreign

The HTTP Foreign listener lets one Empire server generate stagers and agents that report back to a **different** Empire server. The foreign listener holds just enough of the remote listener's configuration to produce a compatible launcher; the agents that call home are managed by the *other* server, not this one.

## Key Configuration Options

### StagingKey

The staging key of the **target** listener. It must match exactly, or the generated agent will fail its initial key negotiation.

### RoutingPacket

The routing packet extracted from the targeted listener, used so the foreign agent's traffic is routed correctly on the remote server.

### Cookie

The custom cookie name used for agent communication (default `session`). Match it to the target listener.

### Host / Port and default agent settings

`Host` and `Port` point at the target server's staging endpoint. `DefaultDelay`, `DefaultJitter`, `DefaultLostLimit`, and `DefaultProfile` behave exactly as they do on the standard HTTP listener and should mirror the target listener's profile. `KillDate` and `WorkingHours` are optional.

## When to use

Use a foreign listener for hand-offs between operators or servers — for example, staging an agent from an infrastructure server that will be managed on a separate team server.

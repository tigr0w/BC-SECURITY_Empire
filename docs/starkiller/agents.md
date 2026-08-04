# Agents

The **Agents** screen lists every session that has checked in. It is where you drill into a single agent to task it, browse its filesystem, and review its history.

## The agents list

Each row is one agent. The default columns show its name, when it was first and last seen, the hostname, the process it is running in, the language, the user context, and the internal IP.

![](../.gitbook/assets/agents_tab.png)

An agent that turns **red** is *stale*: it has missed enough check-ins that the server can no longer reach it. A healthy agent keeps the default colour and updates its last-seen time on each check-in.

## Interacting with an agent

Clicking a row opens the agent's detail view, a tabbed workspace.

**Interact** is the default tab. Task the agent by running a module, dropping to an interactive shell, or opening a full terminal.

![](../.gitbook/assets/agent_interact.png)

**File Browser** walks the agent's filesystem as a tree. Folders expand on click. The listing shown is the last one the agent returned; expanding a folder Empire has not enumerated yet queues a fresh directory task.

![](../.gitbook/assets/agent_file_browser.png)

**Tasks** lists every tasking issued to this agent and its status. See [Agent Tasks](agent-tasks.md) for what each status means.

**Jobs** shows long-running tasks, such as keyloggers, that keep returning output.

**Stats** charts the agent's check-in history over time.

**View** holds the agent's configuration: its delay, jitter, and the host details Empire has collected.

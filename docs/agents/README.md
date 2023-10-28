# Empire Agents Overview
This page provides an in-depth overview of the different agents available within Empire, including their capabilities, features, and usage scenarios.

## IronPython Agent
IronPython brings the Python language to the .NET framework. The IronPython agent leverages this to execute Python scripts using .NET, bypassing restrictions on native Python interpreters. Additional documentation on the agent can be found [here](./python/README.md).

### Features
- Executes in a .NET context, allowing for unique evasion techniques.
- Can interface with .NET libraries directly from Python code.
- Runs Python, C#, and PowerShell taskings.

## Python Agent
The Python agent offers cross-platform capabilities for targeting non-Windows systems, such as Linux and macOS. Additional documentation on the agent can be found [here](./python/README.md).

## Features
- Cross-platform for Linux and macOS.

## PowerShell Agent
The PowerShell agent is the original agent for Empire.

# Features:
- Reflectively loads into memory.
- Can run C# and PowerShell taskings.

## C# Agent
The C# agent leverages [Sharpire](https://github.com/BC-SECURITY/Sharpire) as the implant.

### Features
- Can run C# and PowerShell taskings.

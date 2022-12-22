![Empire](https://user-images.githubusercontent.com/20302208/70022749-1ad2b080-154a-11ea-9d8c-1b42632fd9f9.jpg)

[![Docs](https://img.shields.io/badge/Wiki-Docs-green?style=plastic&logo=wikipedia)](https://bc-security.gitbook.io/empire-wiki/)
[![Twitter URL](https://img.shields.io/twitter/follow/BCSecurity1?style=plastic&logo=twitter)](https://twitter.com/BCSecurity1)
[![YouTube URL](https://img.shields.io/youtube/channel/views/UCIV4xSntF1h1bvFt8SUfzZg?style=plastic&logo=youtube)](https://www.youtube.com/channel/UCIV4xSntF1h1bvFt8SUfzZg)
[![Discord](https://img.shields.io/discord/716165691383873536?style=plastic&logo=discord)](https://discord.gg/P8PZPyf)
[![Donate](https://img.shields.io/badge/Donate-Sponsor-blue?style=plastic&logo=github)](https://github.com/sponsors/BC-SECURITY)
[![Blog](https://img.shields.io/badge/Blog-Read%20me-orange?style=plastic&logo=wordpress)](https://www.bc-security.org/blog)

# Empire
Empire is a post-exploitation and adversary emulation framework that is used to aid Red Teams and Penetration Testers. The Empire server is written in Python 3 and is modular to allow operator flexibility. Empire comes built-in with a client that can be used remotely to access the server. There is also a GUI available for remotely accessing the Empire server, [Starkiller](https://github.com/BC-SECURITY/Starkiller).

### Features
- Server/Client Architecture for Multiplayer Support
- Supports GUI & CLI Clients
- Fully encrypted communications
- HTTP/S, Malleable HTTP, OneDrive, Dropbox, and PHP Listeners
- Massive library (400+) of supported tools in PowerShell, C#, & Python
- Donut Integration for shellcode generation
- Modular plugin interface for custom server features
- Flexible module interface for adding new tools
- Integrated obfuscation using [ConfuserEx 2](https://github.com/mkaring/ConfuserEx) & [Invoke-Obfuscation](https://github.com/danielbohannon/Invoke-Obfuscation)
- In-memory .NET assembly execution
- Customizable Bypasses
- JA3/S and JARM Evasion
- MITRE ATT&CK Integration
- Integrated Roslyn compiler (Thanks to [Covenant](https://github.com/cobbr/Covenant))
- Docker, Kali, Ubuntu, and Debian Install Support

### Agents
- PowerShell
- Python 3
- C#
- IronPython 3

### Modules
- [Assembly Execution](https://github.com/BC-SECURITY/Empire/blob/master/empire/server/data/module_source/code_execution/Invoke-Assembly.ps1)
- [BOF Execution](https://github.com/airbus-cert/Invoke-Bof)
- [Mimikatz](https://github.com/gentilkiwi/mimikatz)
- [Seatbelt](https://github.com/GhostPack/Seatbelt)
- [Rubeus](https://github.com/GhostPack/Rubeus)
- [SharpSploit](https://github.com/cobbr/SharpSploit)
- [Certify](https://github.com/GhostPack/Certify)
- [ProcessInjection](https://github.com/3xpl01tc0d3r/ProcessInjection)
- And Many More

## Sponsors
[<img src="https://user-images.githubusercontent.com/20302208/185247407-46b00d46-0468-4600-9c0d-4efeedc38b3b.png" height="100"/>](https://www.kali.org/) &emsp; &emsp; &emsp;
[<img src="https://user-images.githubusercontent.com/20302208/185246508-56f4f574-5a06-4a2c-ac62-320922588dcf.png" width="100"/>](https://www.sans.org/cyber-security-courses/red-team-operations-adversary-emulation/) &emsp; &emsp; &emsp;
[<img src="https://user-images.githubusercontent.com/20302208/113086242-219d2200-9196-11eb-8c91-84f19c646873.png" width="100"/>](https://kovert.no/) &emsp; &emsp; &emsp;
[<img src="https://user-images.githubusercontent.com/20302208/208271681-235c914b-5359-426e-8a3d-903bbd018847.png" width="100"/>](https://www.cybrary.it/)


## Release Notes

Please see our [Releases](https://github.com/BC-SECURITY/Empire/releases) or [Changelog](/changelog) page for detailed release notes.

###  Quickstart
Empire has server client architecture which requires running each in separate terminals. 
Check out the [Installation Page](https://bc-security.gitbook.io/empire-wiki/quickstart/installation) for install instructions.

Note: The `main` branch is a reflection of the latest changes and may not always be stable.
After cloning the repo, you can checkout the latest stable release by running the `setup/checkout-latest-tag.sh` script.
```bash
git clone --recursive https://github.com/BC-SECURITY/Empire.git
cd Empire
./setup/checkout-latest-tag.sh
sudo ./setup/install.sh
```

#### Server

```bash
# Start Server
./ps-empire server

# Help
./ps-empire server -h
```

#### Client

```bash
# Start Client
./ps-empire client

# Help
./ps-empire client -h
```

Check out the [Empire Docs](https://bc-security.gitbook.io/empire-wiki/) for more instructions on installing and using with Empire.
For a complete list of the 4.0 changes, see the [changelog](./changelog).

## Starkiller
<div align="center"><img width="125" src="https://user-images.githubusercontent.com/20302208/208271792-91973457-2d6c-4080-8625-0f9eebed0a82.png"></div>

[Starkiller](https://github.com/BC-SECURITY/Starkiller) is a GUI for PowerShell Empire that interfaces remotely with Empire via its API. Starkiller can be ran as a replacement for the Empire client or in a mixed environment with Starkiller and Empire clients.

## Contribution Rules
See [Contributing](./.github/CONTRIBUTING.md)

## Contributors
A special thanks to the following contributors for their help with Empire:

[@harmj0y](https://twitter.com/harmj0y)
[@sixdub](https://twitter.com/sixdub)
[@enigma0x3](https://twitter.com/enigma0x3)
[@rvrsh3ll](https://twitter.com/424f424f)
[@killswitch_gui](https://twitter.com/killswitch_gui)
[@xorrior](https://twitter.com/xorrior)
[@Cx01N](https://twitter.com/Cx01N_)
[@Hubbl3](https://twitter.com/_Hubbl3)
[@Vinnybod](https://twitter.com/_vinnybod)

## Official Discord Channel
Join us in [our Discord](https://discord.gg/P8PZPyf) to with any comments, questions, concerns, or problems!

<p align="center">
<a href="https://discord.gg/P8PZPyf">
<img src="https://discordapp.com/api/guilds/716165691383873536/widget.png?style=banner3"/>
</p>

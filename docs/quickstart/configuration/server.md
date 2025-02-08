# Server

The Server configuration is managed via [empire/server/config.yaml](https://github.com/BC-SECURITY/Empire/blob/master/empire/client/config.yaml).

Once launched, Empire checks for user write permissions on paths specified in `config.yaml`. If the current user does not have write permissions on these paths, `~/.empire` will be set as fallback parent directory and the configuration file will be updated as well.
If `empire-priv.key` and `empire-chain.pem` are not found in ~/.local/share/empire directory, self-signed certs will be generated.

* **suppress-self-cert-warning** - Suppress the http warnings when launching an Empire instance that uses a self-signed cert.

* **api** - Configure the RESTful API.

ip - The IP address to bind the API and Starkiller to.
port - The port to bind the API and Starkiller to.
secure - Enable HTTPS for the API and Starkiller. Browsers will not work with self-signed certs. Uses .key and .pem file from empire/server/data

```yaml
api:
  ip: 0.0.0.0
  port: 1337
  secure: false
```

* **database** - Configure Empire's database. Empire defaults to SQLite and has the ability to run with MySQL. For more info on the database, see the [Database](database/README.md) section.

SQLite - The location of the SQLite db file is configurable.

```yaml
database:
  use: sqlite
  sqlite:
    location: empire/server/data/empire.db
```

MySQL - The url, username, password, and database name are all configurable.

```yaml
database:
  use: mysql
  mysql:
    url: localhost
    username:
    password:
    database_name:
```

The defaults block defines the properties that are initially loaded into the database when it is first created.

```yaml
database:
  defaults:
    # staging key will first look at OS environment variables, then here.
    # If empty, will be prompted (like Empire <3.7).
    staging-key: RANDOM
    username: empireadmin
    password: password123
    # The default configuration for global obfuscation.
    obfuscation:
      - language: powershell
        enabled: false
        command: "Token\\All\\1"
        module: "invoke-obfuscation"
        preobfuscatable: true
      - language: csharp
        enabled: false
        command: ""
        module: "confuser"
        preobfuscatable: false
    ip_allow_list: []
    ip_deny_list: []
    keyword_obfuscation:
      - Invoke-Empire
      - Invoke-Mimikatz
```

* **empire_compiler** - Configure the Empire Compiler module. This block manages settings for the Empire Compiler, which is responsible for handling C# compilation tasks.

enabled: Enable or disable the Empire Compiler module.
version: Specify the version of the Empire Compiler to use.
repo: Repository location for the Empire Compiler.
directory: Directory path where the Empire Compiler is installed.
auto_update: Automatically update the Empire Compiler on startup.

```yaml
empire_compiler:
  enabled: true
  version: v0.2
  repo: git@github.com:BC-SECURITY/Empire-Compiler.git
  directory: empire/server/Empire-Compiler
  auto_update: true
```


* **plugins** - Config related to plugins
auto_start - boolean, whether the plugin should start automatically. If this is not set, Empire will defer to the plugin's own configuration.
auto_execute - run an execute command on the plugin at startup. If this is not set, Empire will defer to the plugin's own configuration.

```yaml
plugins:
  # Auto-execute plugin with defined settings
  basic_reporting:
    auto_start: true
    auto_execute:
      enabled: true
      options:
        report: all
```

* **directories** - Control where Empire should read and write specific data.

```yaml
directories:
  downloads: downloads
```

* **logging** - See [Logging](../../logging/logging.md) for more information on logging configuration.

* **submodules** - Control if submodules wil be auto updated on startup.

```
submodules:
  auto_update: true
```

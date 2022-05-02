V2 API Docs
-----------

**These docs are for Empire 5.0 while its in development and will move to the empire-docs repo when its ready**

## Introduction
The V2 API is a RESTful API that provides access to the data in Empire.
The API is powered by [FastAPI](https://fastapi.tiangolo.com/) and is available at [http://localhost:8000/api/v2beta/](http://localhost:8000/api/v2beta/).
The Swagger UI is available at [http://localhost:8000/docs/](http://localhost:8000/docs/).
The docs here are to be used as a reference for the API and to explain nuances for interacting with it. For actual endpoint definitions,
use the OpenAPI Spec. For explanations of what the heck a listener, stager, etc is, see the associated non-API documentation.

## Endpoints

#### Listener Templates
*/api/v2beta/listener-templates/*
Listener templates are the "types" of templates that can be used to create listeners.
A listener template defines the options that can be used when creating a listener.
Listener templates are read-only via the API.
```json
{
}
```
The options that are listed are derived from the associated listener objects. The `value` field will always be a string,
for a consistent API object, but the `type` field will tell the client how to interpret the value.

#### Listeners
*/api/v2beta/listeners/*
Listeners are created by using a listener template. The create endpoint expects the
options dictionary to contain the options that are required for associated listener template
and will be validated against the template. The options can be sent as strings, but Empire will
still validate that they can be parsed to the correct type and raise an exception if it isn't correct.
```json
{
  "todo": "example options"
}
```
They can be created, updated, enabled/disabled, and deleted via the API. To update a listener,
it must be disabled first.

### Stager Templates
*/api/v2beta/stager-templates/*
Stager templates are the "types" of templates that can be used to create stagers.
A stager template defines the options that can be used when creating a stagers.
Stager templates are read-only via the API.
```json
{
  "todo": "example options"
}
```
The options that are listed are derived from the associated stager objects. The `value` field will always be a string,
for a consistent API object, but the `type` field will tell the client how to interpret the value.

### Stagers
*/api/v2beta/stagers/*
Stagers are created by using a stager template. The create endpoint expects the
options dictionary to contain the options that are required for associated stager template
and will be validated against the template. The options can be sent as strings, but Empire will
still validate that they can be parsed to the correct type and raise an exception if it isn't correct.
```json
{
  "todo": "example options"
}
```
They can be created, updated, and deleted via the API. 
When creating a stager, there is an option to only "generate" instead of save.
If `save=false`, then the stager will not be saved to the database, but will be returned in the response. If the stager is a file, then the response will contain a reference to the download uri for that file.

### Agents
*/api/v2beta/agents/*
The agent endpoints allow for updating specific fields and deleting (aka killing or archiving).
The agent endpoints also have sub-resources for tasks and files.

#### Agent Tasks
*/api/v2beta/agents/{agent_id}/tasks/*
The agent tasks endpoints are for tasking an agent to do something.
While there are a variety of `POST` endpoints for specific types of tasks, the resulting
objects are the same and can be viewed together via the `GET` endpoints. Tasks also support deletion as long as they are still only queued to run (the agent hasn't seen it yet).

Some tasks have the ability to join in a `Download`, if this is the case, the downloads will appear as a property on the task response with a reference to the uri.

#### Agent Files
*/api/v2beta/agents/{agent_id}/files/*
The agent files endpoints are a read only view of the the files on an agent's machine.
To populate agent files, a task must be run to get a list of files. At the moment running an `ls`
will populate this resource because of a [hook](todo) that is built in to Empire. There is also a `DirectoryList` task that also populates these, which is what the File Browser in Starkiller uses.

If a file is downloaded, then the associated AgentFile record will have a joined `Download` record. Just like Stagers and Agent Tasks, if a download is associated with a file, it will be returned along with the file with a reference to the uri to download it.

### Modules
*/api/v2beta/modules/*
The modules endpoints provide a way to view the currently loaded modules in Empire.
At the moment, there is no way to create modules via the API, the must exist on the server
at the time that the server is ran. There is an update endpoint that allows for enabling and disabling a module. Disabling a module will block it from being allowed to execute.

### Hosts
*/api/v2beta/hosts/*
Hosts are read-only via the API. Hosts represent the machines that agents are running on.
Multiple agents can run on a single host. The resources are generated when an agent connects and
is based on its internal IP address and name.

### Host Processes
*/api/v2beta/hosts/{host_id}/host-processes/*
<!-- TODO This still needs to be implemented. Still have not landed on what the API looks -->
<!--   like since we might switch to using a tree instead of a list. -->
Host processes are read-only via the API. 

### Downloads
*/api/v2beta/downloads*
The downloads API allows for downloading of files from the Empire server.
Downloads are linked to the following sources (and can be expanded in the future):
* Saved stagers
* Downloaded agent files, such as via the file browser or a task
* Agent tasks

A user can also upload a file to the server via the `POST` endpoint. That file can then
be referenced to be used in certain modules. (TODO this is only somewhat implemented via 4.x).

### Credentials
*/api/v2beta/credentials*
Credentials support basic CRUD operations via the API.
They can also be generated by agent tasks.

#### Obfuscation
### Keywords
*/api/v2beta/obfuscation/keywords*
Credentials support basic CRUD operations via the API.
These are used for the `keyword replacement` feature within Empire.

### Global Obfuscation
*/api/v2beta/obfuscation/global*
The global obfuscation endpoint allows for getting and modifying the global obfuscation configuration
for a language. At the moment, only `powershell` is supported. Global obfuscation is used for obfuscating
module payloads. Modules can be pre-obfuscated by using the `/preobfuscate` endpoint.

### Bypasses
*/api/v2beta/bypasses*
Bypasses support basic CRUD operations via the API.
Once created, these can be passed into the `Bypasses` field of a stager.

### Malleable Profiles
*/api/v2beta/malleable-profiles*
Malleable Profiles support basic CRUD operations via the API.
They are initially loaded via .profile files on Empire startup, and then can be change via the API. Once created, they can be passed as an option to the malleable listener.

### Plugins
*/api/v2beta/plugins*
The plugin endpoints allow for the management of plugins. There is an endpoint for getting a single plugin, as well as a list of all plugins.
The `execute` endpoint allows for the execution of a plugin's code. Like a listener, stager, or module, the plugin defines its options in code, and the options can be sent as strings, but Empire will still validate that they can be parsed to the correct type and raise an exception if it isn't correct.

### Meta
*/api/v2beta/meta*
The meta endpoints are for getting information about the server itself.
At the moment, there is only an endpoint for getting the version of the server.

### Users
*/api/v2beta/users*
Users support basic CRUD operations via the API.
There is also an endpoint for updating a user's password. Only an admin user can create and
update other users.

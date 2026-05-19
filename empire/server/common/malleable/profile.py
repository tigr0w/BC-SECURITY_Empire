import base64
import json
import logging
import string

from pyparsing import *
from six.moves import range

from .implementation import Get, Post, Stager
from .transaction import MalleableRequest, MalleableResponse
from .transformation import Container, Terminator, Transform
from .utility import MalleableError, MalleableObject, MalleableUtil

log = logging.getLogger(__name__)

# Schema version for the JSON profile blob consumed by C#/Go agents.
# Bump when making a backwards-incompatible change — both Sharpire and
# Gopire parse `v` and will refuse unknown versions.
_AGENT_PROFILE_SCHEMA_VERSION = 1

# Top-level `set X "Y";` directives the parser honors. Anything in this set
# goes through normal attribute assignment (which also runs property setters
# like Profile.useragent).
_WIRED_UP_SET_KEYS = frozenset(
    {
        "useragent",
        "sleeptime",
        "jitter",
        "host_stage",
        "sample_name",
    }
)

# `set X "Y";` directives present in shipped Cobalt Strike profiles that
# Empire accepts but does not yet act on. Stored on the instance for
# inspection / forward-compat but not used by the runtime.
#
# IMPORTANT: this set must cover *every* `set` keyword used by shipped
# profiles under empire/server/data/profiles/. The catch is that pyparsing's
# ZeroOrMore in Profile._pattern() greedily resyncs around unrecognised
# blocks (http-config, https-certificate, stage, process-inject, post-ex,
# dns-beacon, …), so `set` directives *inside* those blocks leak out and
# parse as top-level directives. Until Tiers 1/3/4 add real block parsers,
# we list those leaked keys here so the parser stays quiet on existing
# profiles. The grouping comments mark which roadmap tier should drain
# the key out of this set into a real wiring.
#
# Audit: `grep -rhE '^\s*set [A-Za-z_]' empire/server/data/profiles/ \
#   | grep -oE 'set [A-Za-z_][A-Za-z_0-9]*' | awk '{print $2}' | sort -u`
# Re-run when adding a new shipped profile and reconcile with this set —
# the TestShippedProfilesAllowList test will fail if drift goes uncaught.
_ACCEPTED_BUT_IGNORED_SET_KEYS = frozenset(
    {
        # dns-beacon block / DNS C2 (roadmap Tier 5 — deferred)
        "beacon",
        "data_jitter",
        "dns_idle",
        "dns_max_txt",
        "dns_sleep",
        "dns_stager_prepend",
        "dns_stager_subhost",
        "dns_ttl",
        "get_a",
        "get_aaaa",
        "get_txt",
        "maxdns",
        "name",  # DNS beacon name; case-insensitive lowercase here
        "ns_response",
        "put_metadata",
        "put_output",
        # https-certificate block (roadmap Tier 1)
        "c",
        "cn",
        "keystore",
        "l",
        "o",
        "ou",
        "password",
        "st",
        "validity",
        # http-config block (roadmap Tier 1)
        "block_useragents",
        "headers",
        "trust_x_forwarded_for",
        "verb",
        # stage block (roadmap Tier 3)
        "checksum",
        "cleanup",
        "compile_time",
        "entry_point",
        "image_size_x64",
        "image_size_x86",
        "magic_mz_x64",
        "magic_mz_x86",
        "magic_pe",
        "module_x64",
        "module_x86",
        "obfuscate",
        "rich_header",
        "sleep_mask",
        "smartinject",
        "stomppe",
        "userwx",
        # http-stager block (roadmap Tier 2 — stager-block transforms / URIs)
        "uri",
        "uri_x64",
        "uri_x86",
        # process-inject block (roadmap Tier 4)
        "allocator",
        "hijack_remote_thread",
        "min_alloc",
        "spawnto",
        "spawnto_x64",
        "spawnto_x86",
        "startrwx",
        # post-ex block (roadmap Tier 3)
        "amsi_disable",
        "keylogger",
        "pipename",
        "pipename_stager",
        "thread_hint",
        # SMB / TCP / SSH transports (out of scope for current tiers)
        "smb_frame_header",
        "ssh_banner",
        "ssh_pipename",
        "tcp_frame_header",
        "tcp_port",
    }
)

# Type normalization for wired-up scalar keys. The parser produces strings,
# so without this `set host_stage "false";` would store the truthy string
# "false" — silently wrong. `set sleeptime "60000";` historically worked
# only because downstream code re-wrapped it in int().
_BOOL_SET_KEYS = frozenset({"host_stage"})
_INT_SET_KEYS = frozenset({"sleeptime", "jitter"})

# Truthy literal values accepted for boolean `set` directives. Anything else
# (including the empty string) is treated as False — matching Cobalt Strike's
# documented convention for boolean profile fields.
_TRUTHY_LITERALS = frozenset({"true", "1", "yes", "on"})


def _normalize_set_value(key: str, raw: str):
    """Coerce a string-valued `set <key> "<raw>";` value to its typed form.

    Booleans are case-insensitive: only the literals in _TRUTHY_LITERALS map
    to True. Integers raise no exception — if the operator wrote a non-numeric
    value, ``int()`` will throw and the caller logs + drops the directive.
    """
    if key in _BOOL_SET_KEYS:
        return raw.strip().lower() in _TRUTHY_LITERALS
    if key in _INT_SET_KEYS:
        return int(raw)
    return raw

# Transform.type -> JSON "op" string. NONE is intentionally absent so it
# falls through to the "skip" branch in the serializer.
#
# NOTE on append/prepend: the "value" field is emitted as base64 of the
# raw bytes (latin-1 in the Python model). A plain JSON string would
# UTF-8-encode any high-bit byte and silently grow it from 1 byte to 2,
# breaking byte-exact parity with the PowerShell/Python server transforms
# on the other side. Both Sharpire (C#) and Gopire (Go) base64-decode
# this field before concatenation.
_TRANSFORM_OP_NAMES = {
    Transform.APPEND: "append",
    Transform.PREPEND: "prepend",
    Transform.BASE64: "base64",
    Transform.BASE64URL: "base64url",
    Transform.NETBIOS: "netbios",
    Transform.NETBIOSU: "netbiosu",
    Transform.MASK: "mask",
}

# Terminator.type -> JSON "type" string.
_TERMINATOR_TYPE_NAMES = {
    Terminator.HEADER: "header",
    Terminator.PRINT: "print",
    Terminator.PARAMETER: "parameter",
    Terminator.URIAPPEND: "uri-append",
}

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
# PROFILE
#
# Defining the top-layer object to be interacted with.
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #


class Profile(MalleableObject):
    """A class housing all the functionality of a Malleable C2 profile.

    Attributes:
        get (Get (Transaction))
        post (Post (Transaction))
        stager (Stager (Transaction))

        useragent (str, property)
        sleeptime (int) [milliseconds]
        jitter (int) [percent]
    """

    def _defaults(self):
        """Default initialization for the Profile object."""
        super()._defaults()
        self.get = Get()
        self.post = Post()
        self.stager = Stager()
        self.sleeptime = 60000
        self.jitter = 0
        # host_stage defaults True so existing profiles keep serving the
        # stager URI; operators opt out by adding `set host_stage "false";`.
        self.host_stage = True
        # sample_name is a free-form attribution tag from the profile author,
        # surfaced in the API but not used by the runtime.
        self.sample_name = None

    def _clone(self):
        """Deep copy of the Profile object.

        Returns:
            Profile
        """
        new = super()._clone()
        new.get = self.get._clone()
        new.post = self.post._clone()
        new.stager = self.stager._clone()
        new.sleeptime = self.sleeptime
        new.jitter = self.jitter
        new.host_stage = self.host_stage
        new.sample_name = self.sample_name
        return new

    def _serialize(self):
        """Serialize the Profile object.

        Returns:
            dict (str, obj): Serialized data (json)
        """
        return dict(
            list(super()._serialize().items())
            + list(
                {
                    "get": self.get._serialize(),
                    "post": self.post._serialize(),
                    "stager": self.stager._serialize(),
                    "sleeptime": self.sleeptime,
                    "jitter": self.jitter,
                    "host_stage": self.host_stage,
                    "sample_name": self.sample_name,
                }.items()
            )
        )

    @classmethod
    def _deserialize(cls, data):
        """Deserialize data into a Profile object.

        Args:
            data (dict (str, obj)): Serialized data (json)

        Returns:
            Profile object
        """
        profile = super()._deserialize(data)
        if data:
            try:
                profile.get = Get._deserialize(data["get"]) if "get" in data else Get()
                profile.post = (
                    Post._deserialize(data["post"]) if "post" in data else Post()
                )
                profile.stager = (
                    Stager._deserialize(data["stager"])
                    if "stager" in data
                    else Stager()
                )
                profile.sleeptime = (
                    int(data["sleeptime"]) if "sleeptime" in data else 60000
                )
                profile.jitter = int(data["jitter"]) if "jitter" in data else 0
                profile.host_stage = bool(data.get("host_stage", True))
                profile.sample_name = data.get("sample_name")
            except Exception as e:
                MalleableError.throw(
                    cls, "_deserialize", "An error occurred: " + str(e)
                )
        return profile

    @classmethod
    def _pattern(cls):
        """Define the pattern to recognize a Profile object while parsing a file.

        Returns:
            pyparsing object
        """
        return ZeroOrMore(
            cls.COMMENT
            | (Literal("set") + Group(cls.FIELD + cls.VALUE) + cls.SEMICOLON)
            | Get._pattern()
            | Post._pattern()
            | Stager._pattern()
        )

    def _parse(self, data):
        """Store the information from a parsed pyparsing result.

        Args:
            data: pyparsing data
        """
        if data:
            for group in [d for d in data if d]:
                for i in range(0, len(group), 2):
                    item = group[i]
                    arg = group[i + 1] if len(group) > i + 1 else None
                    if item and arg:
                        if item.lower() == "set" and len(arg) > 1:
                            key, value = arg[0], arg[1]
                            if key and value:
                                self._apply_set_directive(key, value)
                        elif item.lower() == "http-get":
                            self.get._parse(arg)
                        elif item.lower() == "http-post":
                            self.post._parse(arg)
                        elif item.lower() == "http-stager":
                            self.stager._parse(arg)

    def _apply_set_directive(self, key: str, raw_value: str) -> None:
        """Classify and apply a top-level `set <key> "<raw_value>";` directive.

        Three-way classifier (see module-level allow-lists):
          - wired-up keys flow through normal attribute assignment, with
            type normalization for booleans/integers so `set host_stage
            "false";` round-trips to Python ``False`` rather than the
            truthy string ``"false"``.
          - accepted-but-ignored keys land on the instance verbatim and
            emit one INFO log per directive so operators can audit which
            CS-vocabulary fields the profile uses that Empire does not yet
            honor.
          - unknown keys also land on the instance (preserving the
            historical catch-all behavior so no profile parse hard-fails
            on this change) but emit a WARNING.
        """
        lowered = key.lower()

        if lowered in _WIRED_UP_SET_KEYS:
            try:
                value = _normalize_set_value(lowered, raw_value)
            except (TypeError, ValueError) as exc:
                log.warning(
                    "malleable profile: dropping set %s=%r (cannot normalize: %s)",
                    key,
                    raw_value,
                    exc,
                )
                return
            setattr(self, lowered, value)
            return

        if lowered in _ACCEPTED_BUT_IGNORED_SET_KEYS:
            log.info(
                "malleable profile: accepting `set %s` but Empire does not act on it yet",
                key,
            )
            setattr(self, lowered, raw_value)
            return

        log.warning(
            "malleable profile: unknown directive `set %s %r;` — storing on profile but it will not affect behavior",
            key,
            raw_value,
        )
        setattr(self, lowered, raw_value)

    @property
    def useragent(self):
        """Get the profile useragent.

        Returns:
            str: useragent
        """
        return (
            self.get.client.headers["User-Agent"]
            if "User-Agent" in self.get.client.headers
            else None
        )

    @useragent.setter
    def useragent(self, useragent):
        """Set the profile useragent.

        Args:
            useragent (str)
        """
        self.get.client.headers["User-Agent"] = useragent
        self.post.client.headers["User-Agent"] = useragent
        self.stager.client.headers["User-Agent"] = useragent

    def validate(self):
        """Validate the profile to verify it will succeed when used.

        Returns:
            bool: True if no checks fail.

        Raises:
            MalleableError: If a check fails.
        """
        host = "http://domain.com:80"
        # data = string.printable
        data = string.printable.encode("latin-1")
        for format, p in [
            ("base", self),
            ("clone", self._clone()),
            ("serialized", Profile._deserialize(self._serialize())),
        ]:
            test = p.get.construct_client(host, data)
            clone = MalleableRequest()
            clone.url = test.url
            clone.verb = test.verb
            clone.headers = test.headers
            clone.body = test.body
            if self.get.extract_client(clone) != data:
                MalleableError.throw(
                    self.__class__,
                    "validate",
                    "Data-integrity check failed: %s-get-client-metadata" % format,
                )

            test = p.get.construct_server(data)
            clone = MalleableResponse()
            clone.headers = test.headers
            clone.body = test.body
            if self.get.extract_server(clone) != data:
                MalleableError.throw(
                    self.__class__,
                    "validate",
                    "Data-integrity check failed: %s-get-server-output" % format,
                )

            test = p.post.construct_client(host, data, data)
            clone = MalleableRequest()
            clone.url = test.url
            clone.verb = test.verb
            clone.headers = test.headers
            clone.body = test.body
            id, output = self.post.extract_client(clone)
            if id != data:
                MalleableError.throw(
                    self.__class__,
                    "validate",
                    "Data-integrity check failed: %s-post-client-id" % format,
                )
            if output != data:
                MalleableError.throw(
                    self.__class__,
                    "validate",
                    "Data-integrity check failed: %s-post-client-output" % format,
                )

            test = p.post.construct_server(data)
            clone = MalleableResponse()
            clone.headers = test.headers
            clone.body = test.body
            if self.post.extract_server(clone) != data:
                MalleableError.throw(
                    self.__class__,
                    "validate",
                    "Data-integrity check failed: %s-post-server-output" % format,
                )

            test = p.stager.construct_client(host, data)
            clone = MalleableRequest()
            clone.url = test.url
            clone.verb = test.verb
            clone.headers = test.headers
            clone.body = test.body
            if self.stager.extract_client(clone) != data:
                MalleableError.throw(
                    self.__class__,
                    "validate",
                    "Data-integrity check failed: %s-stager-client-metadata" % format,
                )

            test = p.stager.construct_server(data)
            clone = MalleableResponse()
            clone.headers = test.headers
            clone.body = test.body
            if self.stager.extract_server(clone) != data:
                MalleableError.throw(
                    self.__class__,
                    "validate",
                    "Data-integrity check failed: %s-stager-server-output" % format,
                )

        if (
            set(self.get.client.uris).intersection(set(self.post.client.uris))
            or set(self.post.client.uris).intersection(set(self.stager.client.uris))
            or set(self.stager.client.uris).intersection(set(self.get.client.uris))
            or len(self.get.client.uris + (self.post.client.uris or ["/"])) == 0
            or len(self.post.client.uris + (self.stager.client.uris or ["/"])) == 0
            or len(self.stager.client.uris + (self.get.client.uris or ["/"])) == 0
            or ("/" in self.get.client.uris and len(self.post.client.uris) == 0)
            or ("/" in self.get.client.uris and len(self.stager.client.uris) == 0)
            or ("/" in self.post.client.uris and len(self.stager.client.uris) == 0)
            or ("/" in self.post.client.uris and len(self.get.client.uris) == 0)
            or ("/" in self.stager.client.uris and len(self.get.client.uris) == 0)
            or ("/" in self.stager.client.uris and len(self.post.client.uris) == 0)
        ):
            MalleableError.throw(
                self.__class__,
                "validate",
                "Cannot have duplicate uris: %s - %s - %s"
                % (
                    self.get.client.uris or ["/"],
                    self.post.client.uris or ["/"],
                    self.stager.client.uris or ["/"],
                ),
            )

        return True

    def serialize_for_agent(self) -> str:
        """Serialize this profile to a compact JSON blob for runtime consumption
        by non-PowerShell/Python agents (C# / Sharpire, Go / Gopire).

        The result is inlined into stager templates, so it is emitted with
        ``separators=(",", ":")`` — no whitespace padding. See the schema
        documentation and ``_AGENT_PROFILE_SCHEMA_VERSION`` for the versioned
        contract with downstream agent parsers.

        Returns:
            str: Compact JSON blob.
        """
        payload = {
            "v": _AGENT_PROFILE_SCHEMA_VERSION,
            "sleep": int(self.sleeptime),
            "jitter": int(self.jitter),
            "sections": {
                "stager": self._section_for_agent(
                    self.stager,
                    include_client_output=False,
                ),
                "get": self._section_for_agent(
                    self.get,
                    include_client_output=False,
                ),
                "post": self._section_for_agent(
                    self.post,
                    include_client_output=True,
                ),
            },
        }
        return json.dumps(payload, separators=(",", ":"))

    def _section_for_agent(self, transaction, include_client_output: bool) -> dict:
        """Build the per-section dict (stager / get / post).

        ``include_client_output`` is True only for the Post section, which
        is the only transaction whose client carries both a routing packet
        and a task-result payload.
        """
        client = transaction.client
        server = transaction.server

        # Post stores its routing packet in `.id`; Get/Stager store session
        # metadata in `.metadata`. In the agent-facing JSON both are the
        # "metadata" container — agents don't care about Empire's internal
        # naming.
        client_metadata = getattr(client, "metadata", None)
        if client_metadata is None:
            client_metadata = getattr(client, "id", Container())

        client_block = {
            "verb": client.verb,
            "uris": list(client.uris) if client.uris else [],
            "headers": dict(client.headers) if client.headers else {},
            "parameters": dict(client.parameters) if client.parameters else {},
            # body is base64-encoded bytes for the same reason as
            # append/prepend value — cover payloads can contain high-bit
            # characters in real-world profiles and we want byte-exact
            # parity on the Go/C# agent side.
            "body": self._encode_bytes_for_agent(client.body),
            "metadata": self._container_for_agent(client_metadata),
        }
        if include_client_output:
            client_block["output"] = self._container_for_agent(client.output)

        server_block = {
            "headers": dict(server.headers) if server.headers else {},
            "body_prefix": self._encode_bytes_for_agent(
                getattr(server, "body_prefix", "")
            ),
            "output": self._container_for_agent(server.output),
        }

        return {"client": client_block, "server": server_block}

    @staticmethod
    def _encode_bytes_for_agent(value) -> str:
        """Base64-encode a body / body_prefix / prepend / append value so
        high-bit bytes survive the JSON UTF-8 round-trip. Accepts bytes
        or str (latin-1 fallback for str). None/"" returns "".
        """
        if value is None or value == "":
            return ""
        if isinstance(value, (bytes, bytearray)):
            raw = bytes(value)
        elif isinstance(value, str):
            try:
                raw = value.encode("latin-1")
            except UnicodeEncodeError:
                raw = value.encode("utf-8")
        else:
            return ""
        return base64.b64encode(raw).decode("ascii")

    @staticmethod
    def _container_for_agent(container) -> dict:
        """Serialize a Container (sequence of Transforms + Terminator) to
        the agent JSON shape: ``{"transforms": [...], "terminator": {...}}``.
        """
        if container is None:
            return {
                "transforms": [],
                "terminator": {"type": "print"},
            }

        transforms = []
        for t in getattr(container, "transforms", []) or []:
            entry = Profile._transform_for_agent(t)
            if entry is not None:
                transforms.append(entry)

        return {
            "transforms": transforms,
            "terminator": Profile._terminator_for_agent(container.terminator),
        }

    @staticmethod
    def _transform_for_agent(transform):
        """Map a Transform object to its agent-JSON representation, or None
        if it should be skipped (NONE / unknown type / malformed arg).
        """
        t_type = getattr(transform, "type", Transform.NONE)
        op = _TRANSFORM_OP_NAMES.get(t_type)
        if op is None:
            # NONE or an unrecognized type — drop it rather than crash.
            return None

        arg = getattr(transform, "arg", None)

        if t_type in (Transform.APPEND, Transform.PREPEND):
            # Emit the raw bytes as base64 so high-bit values (e.g. a
            # latin-1 b"\xe9") survive the JSON UTF-8 encoding with their
            # 1-byte length intact. A plain JSON string would expand to
            # two UTF-8 bytes and desync the reverse transform on the
            # agent side.
            if arg is None:
                raw = b""
            elif isinstance(arg, (bytes, bytearray)):
                raw = bytes(arg)
            elif isinstance(arg, str):
                try:
                    raw = arg.encode("latin-1")
                except UnicodeEncodeError:
                    raw = arg.encode("utf-8")
            else:
                raw = b""
            return {"op": op, "value": base64.b64encode(raw).decode("ascii")}

        if t_type == Transform.MASK:
            key_hex = ""
            if arg:
                try:
                    byte = arg[0] if isinstance(arg, (bytes, bytearray)) else arg
                    key_hex = MalleableUtil.to_hex(byte) or ""
                except (TypeError, ValueError, IndexError):
                    key_hex = ""
            return {"op": op, "key": key_hex}

        return {"op": op}

    @staticmethod
    def _terminator_for_agent(terminator) -> dict:
        """Map a Terminator object to its agent-JSON representation.

        An unknown / NONE terminator falls back to ``{"type": "print"}`` so
        the agent always has a usable storage location.
        """
        t_type = getattr(terminator, "type", Terminator.PRINT)
        name = _TERMINATOR_TYPE_NAMES.get(t_type)
        if name is None:
            return {"type": "print"}

        if t_type in (Terminator.HEADER, Terminator.PARAMETER):
            arg = getattr(terminator, "arg", None) or ""
            return {"type": name, "arg": arg}

        return {"type": name}

    def ingest(self, file: str = None, content: str = None):
        """Ingest a profile file into the Profile object.

        Args:
            file (str): Filename to be read and parsed.
        """
        # if not file or not os.path.isfile(file):
        #    MalleableError.throw(self.__class__, "ingest", "Invalid file: %s" % str(file))

        if file:
            with open(file) as f:
                content = f.read()
            if not content:
                MalleableError.throw(
                    self.__class__, "ingest", "Empty file: %s" % str(file)
                )

        self._parse(self._pattern().search_string(content))

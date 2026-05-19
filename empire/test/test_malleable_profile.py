"""Tests for the runtime JSON profile serializer consumed by C#/Go agents.

The Python server already builds the PowerShell/Python stager inline from
`Container.generate_*` helpers. C# and Go agents instead parse a versioned
JSON blob at runtime, so the server needs a single canonical serializer —
``Profile.serialize_for_agent`` — that walks the profile tree and emits
that blob.

These tests pin the v1 schema so the agents (which live in separate
repos / submodules) have a stable contract. Every transform op and
terminator type listed in ``transformation.py`` is round-tripped through
the serializer here; adding a new op will fail these tests until it is
mapped explicitly.
"""

import base64
import json
import re
from pathlib import Path

import pytest

from empire.server.common.malleable.profile import (
    _AGENT_PROFILE_SCHEMA_VERSION,
    Profile,
)
from empire.server.common.malleable.transformation import (
    Transform,
)


def _b64(value: bytes | str) -> str:
    """Helper: base64-encode append/prepend values the way the serializer does."""
    if isinstance(value, str):
        value = value.encode("latin-1")
    return base64.b64encode(value).decode("ascii")


# Directory with real-world .profile fixtures shipped with Empire. Used to
# smoke-test the serializer against non-trivial profiles.
PROFILES_DIR = Path(__file__).resolve().parent.parent / "server" / "data" / "profiles"


def _make_profile():
    """Construct a Profile with sane, explicit defaults for serializer tests.

    We set distinct uris/terminators/headers for each section so assertions
    can easily verify the output routed things into the right slot.
    """
    p = Profile()
    p.sleeptime = 12345
    p.jitter = 17

    # stager
    p.stager.client.uris = ["/stage.php"]
    p.stager.client.headers = {"User-Agent": "StagerAgent", "Accept": "text/html"}
    p.stager.client.metadata.base64()
    p.stager.client.metadata.header("Cookie")
    p.stager.server.headers = {"Server": "Apache/Stage"}
    p.stager.server.output.base64()
    p.stager.server.output.print_()

    # get
    p.get.client.uris = ["/news.php"]
    p.get.client.headers = {"User-Agent": "GetAgent"}
    p.get.client.metadata.base64()
    p.get.client.metadata.prepend("session=")
    p.get.client.metadata.header("Cookie")
    p.get.server.headers = {"Server": "Apache/Get"}
    p.get.server.output.base64()
    p.get.server.output.print_()

    # post
    p.post.client.uris = ["/submit.php"]
    p.post.client.headers = {"User-Agent": "PostAgent"}
    p.post.client.id.netbios()
    p.post.client.id.parameter("id")
    p.post.client.output.base64()
    p.post.client.output.print_()
    p.post.server.headers = {"Server": "Apache/Post"}
    p.post.server.output.base64()
    p.post.server.output.print_()

    return p


class TestSerializeForAgentTopLevel:
    def test_returns_string(self):
        p = Profile()
        blob = p.serialize_for_agent()
        assert isinstance(blob, str)
        # Should be parseable as JSON.
        json.loads(blob)

    def test_is_compact(self):
        p = Profile()
        blob = p.serialize_for_agent()
        # The serializer inlines into stager templates, so it MUST be compact
        # (no spaces after separators).
        assert ", " not in blob
        assert ": " not in blob

    def test_version_field(self):
        p = Profile()
        data = json.loads(p.serialize_for_agent())
        # The emitted "v" must equal the module-level constant; bumping
        # _AGENT_PROFILE_SCHEMA_VERSION is the intentional way to break
        # downstream agents that need to opt in to a new schema.
        assert data["v"] == _AGENT_PROFILE_SCHEMA_VERSION

    def test_gopire_supported_version_matches(self):
        # Cross-language contract pin: Gopire's supportedProfileVersion in
        # empire/server/data/agent/gopire/comms/malleable.go must agree with
        # the Python constant. If they drift, a v2 server will emit blobs
        # that v1 Gopire silently parses with zero-valued new sections —
        # worse than a hard failure.
        gopire = (
            Path(__file__).resolve().parent.parent
            / "server"
            / "data"
            / "agent"
            / "gopire"
            / "comms"
            / "malleable.go"
        )
        # The pattern tolerates an optional Go type annotation (e.g.
        # `const supportedProfileVersion uint8 = 1`) so a future agent-side
        # refactor that adds a type doesn't silently break the cross-language
        # pin. The constant name itself stays anchored.
        match = re.search(
            r"^\s*const\s+supportedProfileVersion(?:\s+\w+)?\s*=\s*(\d+)\s*$",
            gopire.read_text(),
            re.MULTILINE,
        )
        assert match is not None, (
            "supportedProfileVersion not found in Gopire malleable.go"
        )
        assert int(match.group(1)) == _AGENT_PROFILE_SCHEMA_VERSION

    def test_sleep_and_jitter(self):
        p = Profile()
        p.sleeptime = 45000
        p.jitter = 25
        data = json.loads(p.serialize_for_agent())
        assert data["sleep"] == 45000  # noqa: PLR2004
        assert data["jitter"] == 25  # noqa: PLR2004

    def test_sections_present(self):
        p = Profile()
        data = json.loads(p.serialize_for_agent())
        assert set(data["sections"].keys()) == {"stager", "get", "post"}

    def test_each_section_has_client_and_server(self):
        p = Profile()
        data = json.loads(p.serialize_for_agent())
        for name in ("stager", "get", "post"):
            section = data["sections"][name]
            assert "client" in section
            assert "server" in section


class TestSerializeForAgentSectionShape:
    def test_get_client_has_metadata_only(self):
        data = json.loads(_make_profile().serialize_for_agent())
        get_client = data["sections"]["get"]["client"]
        assert "metadata" in get_client
        assert "output" not in get_client

    def test_stager_client_has_metadata_only(self):
        data = json.loads(_make_profile().serialize_for_agent())
        stager_client = data["sections"]["stager"]["client"]
        assert "metadata" in stager_client
        assert "output" not in stager_client

    def test_post_client_has_both_metadata_and_output(self):
        data = json.loads(_make_profile().serialize_for_agent())
        post_client = data["sections"]["post"]["client"]
        assert "metadata" in post_client
        assert "output" in post_client

    def test_server_side_has_output(self):
        data = json.loads(_make_profile().serialize_for_agent())
        for name in ("stager", "get", "post"):
            server = data["sections"][name]["server"]
            assert "output" in server
            assert "headers" in server
            assert "body_prefix" in server

    def test_client_basic_fields(self):
        data = json.loads(_make_profile().serialize_for_agent())
        get_client = data["sections"]["get"]["client"]
        assert get_client["verb"] == "GET"
        assert get_client["uris"] == ["/news.php"]
        assert get_client["headers"]["User-Agent"] == "GetAgent"
        assert "parameters" in get_client
        assert "body" in get_client

    def test_post_verb(self):
        data = json.loads(_make_profile().serialize_for_agent())
        assert data["sections"]["post"]["client"]["verb"] == "POST"


class TestTransformOpMapping:
    def _serialize_get_metadata(self, configure):
        """Build a Profile with the given configurator applied to get.client.metadata
        and return the serialized transforms list.
        """
        p = Profile()
        configure(p.get.client.metadata)
        data = json.loads(p.serialize_for_agent())
        return data["sections"]["get"]["client"]["metadata"]["transforms"]

    def test_base64(self):
        transforms = self._serialize_get_metadata(lambda c: c.base64())
        assert transforms == [{"op": "base64"}]

    def test_base64url(self):
        transforms = self._serialize_get_metadata(lambda c: c.base64url())
        assert transforms == [{"op": "base64url"}]

    def test_netbios(self):
        transforms = self._serialize_get_metadata(lambda c: c.netbios())
        assert transforms == [{"op": "netbios"}]

    def test_netbiosu(self):
        transforms = self._serialize_get_metadata(lambda c: c.netbiosu())
        assert transforms == [{"op": "netbiosu"}]

    def test_append(self):
        transforms = self._serialize_get_metadata(lambda c: c.append("tail"))
        # append/prepend value is base64-encoded raw bytes (latin-1 source).
        assert transforms == [{"op": "append", "value": _b64("tail")}]

    def test_prepend(self):
        transforms = self._serialize_get_metadata(lambda c: c.prepend("head="))
        assert transforms == [{"op": "prepend", "value": _b64("head=")}]

    def test_prepend_high_bit_bytes_roundtrip(self):
        """A latin-1 b"\\xe9" should round-trip through base64 as 1 byte.

        Shipping it as a plain JSON string would UTF-8 encode it into 2
        bytes (0xC3 0xA9), breaking byte-exact parity with the
        PowerShell/Python server transforms.
        """
        transforms = self._serialize_get_metadata(
            lambda c: c.prepend(b"caf\xe9".decode("latin-1"))
        )
        # b"caf\xe9" -> base64 "Y2Fm6Q=="
        assert transforms == [{"op": "prepend", "value": "Y2Fm6Q=="}]
        # The decoded length matches the raw byte length (4), NOT the
        # UTF-8 length (5) that a plain JSON string would produce.
        decoded = base64.b64decode(transforms[0]["value"])
        assert decoded == b"caf\xe9"
        assert len(decoded) == len(b"caf\xe9")

    def test_mask_emits_lowercase_hex_key(self):
        transforms = self._serialize_get_metadata(
            lambda c: c.transforms.append(Transform(type=Transform.MASK, arg=b"\x42"))
        )
        assert transforms == [{"op": "mask", "key": "42"}]
        # key is 2 hex chars, lowercase
        assert transforms[0]["key"] == transforms[0]["key"].lower()
        assert len(transforms[0]["key"]) == 2  # noqa: PLR2004

    def test_none_transform_is_skipped(self):
        transforms = self._serialize_get_metadata(
            lambda c: c.transforms.append(Transform(type=Transform.NONE))
        )
        assert transforms == []

    def test_transform_ordering_preserved(self):
        transforms = self._serialize_get_metadata(
            lambda c: (c.base64(), c.prepend("hdr="), c.append(";end"))
        )
        assert transforms == [
            {"op": "base64"},
            {"op": "prepend", "value": _b64("hdr=")},
            {"op": "append", "value": _b64(";end")},
        ]


class TestTerminatorMapping:
    def _serialize_get_metadata_terminator(self, configure):
        p = Profile()
        configure(p.get.client.metadata)
        data = json.loads(p.serialize_for_agent())
        return data["sections"]["get"]["client"]["metadata"]["terminator"]

    def test_header(self):
        term = self._serialize_get_metadata_terminator(lambda c: c.header("Cookie"))
        assert term == {"type": "header", "arg": "Cookie"}

    def test_print(self):
        term = self._serialize_get_metadata_terminator(lambda c: c.print_())
        assert term == {"type": "print"}

    def test_parameter(self):
        term = self._serialize_get_metadata_terminator(lambda c: c.parameter("q"))
        assert term == {"type": "parameter", "arg": "q"}

    def test_uriappend(self):
        term = self._serialize_get_metadata_terminator(lambda c: c.uriappend())
        assert term == {"type": "uri-append"}

    def test_default_terminator_type_print(self):
        # A fresh Container() defaults to Terminator(type=PRINT). Make sure
        # we map it to {"type": "print"} rather than emitting None / unknown.
        p = Profile()
        data = json.loads(p.serialize_for_agent())
        term = data["sections"]["get"]["client"]["metadata"]["terminator"]
        assert term == {"type": "print"}


class TestPostClientRouting:
    """Post client has BOTH a routing packet container (id) and an output container."""

    def test_post_metadata_is_routing_packet(self):
        """The 'metadata' key in post.client maps to Empire's `Post.client.id`
        (the routing packet / session id container)."""
        p = Profile()
        p.post.client.id.base64()
        p.post.client.id.parameter("sess")
        p.post.client.output.netbios()
        p.post.client.output.print_()

        data = json.loads(p.serialize_for_agent())
        post_client = data["sections"]["post"]["client"]

        assert post_client["metadata"]["transforms"] == [{"op": "base64"}]
        assert post_client["metadata"]["terminator"] == {
            "type": "parameter",
            "arg": "sess",
        }
        assert post_client["output"]["transforms"] == [{"op": "netbios"}]
        assert post_client["output"]["terminator"] == {"type": "print"}


class TestRealProfile:
    """Smoke-test against a bundled real profile, if one exists."""

    def _find_profile(self):
        if not PROFILES_DIR.is_dir():
            return None
        for candidate in sorted(PROFILES_DIR.rglob("*.profile")):
            return candidate
        return None

    def test_ingest_and_serialize_roundtrip(self):
        path = self._find_profile()
        if not path:
            pytest.skip("No bundled .profile fixtures found")

        p = Profile()
        p.ingest(file=str(path))
        blob = p.serialize_for_agent()
        data = json.loads(blob)

        # Structural sanity: required keys present.
        assert data["v"] == 1
        assert "sleep" in data
        assert "jitter" in data
        for name in ("stager", "get", "post"):
            section = data["sections"][name]
            assert isinstance(section["client"]["uris"], list)
            assert isinstance(section["client"]["headers"], dict)
            assert isinstance(section["client"]["metadata"]["transforms"], list)
            assert "type" in section["client"]["metadata"]["terminator"]
            assert isinstance(section["server"]["output"]["transforms"], list)
            assert "type" in section["server"]["output"]["terminator"]

        assert "metadata" in data["sections"]["post"]["client"]
        assert "output" in data["sections"]["post"]["client"]


class TestInvalidInput:
    def test_unknown_transform_type_is_omitted(self):
        """If someone pokes a Transform with an unrecognized type into a
        Container, the serializer should drop it rather than crash or emit
        garbage — the agent spec only defines the mapped ops."""
        p = Profile()
        rogue = Transform.__new__(Transform)
        rogue.type = 9999  # not any defined Transform constant
        rogue.arg = None
        p.get.client.metadata.transforms.append(rogue)

        # Should not raise; unknown op is silently dropped.
        data = json.loads(p.serialize_for_agent())
        assert data["sections"]["get"]["client"]["metadata"]["transforms"] == []

    def test_mask_with_invalid_arg_does_not_crash(self):
        """Mask requires a length-1 bytes arg; a malformed value should not
        blow up the whole serializer — emit best-effort or drop, but return."""
        p = Profile()
        bad = Transform.__new__(Transform)
        bad.type = Transform.MASK
        bad.arg = None  # missing key
        p.get.client.metadata.transforms.append(bad)

        # Should not raise.
        blob = p.serialize_for_agent()
        data = json.loads(blob)
        # Either dropped or emitted with empty/omitted key — but not a crash.
        masks = [
            t
            for t in data["sections"]["get"]["client"]["metadata"]["transforms"]
            if t.get("op") == "mask"
        ]
        for m in masks:
            # If present, key must still be a string (possibly empty).
            assert isinstance(m.get("key", ""), str)


class TestTier0SetDirectiveClassifier:
    """Tier 0: the top-level `set` directive parser is a three-way classifier
    (wired-up / accepted-but-ignored / unknown). Previously a single
    setattr() catch-all silently stored everything as a string, so
    `set host_stage "false";` produced a truthy attribute.
    """

    # Minimal http-get/http-post/http-stager skeleton so Profile.ingest
    # accepts the test profile body. The exact transports don't matter —
    # we're only exercising the top-level `set` parser.
    _SKELETON = """
http-get {
    set uri "/";
    client {
        metadata {
            base64;
            header "Cookie";
        }
    }
    server {
        output {
            base64;
            print;
        }
    }
}

http-post {
    set uri "/submit.php";
    client {
        id {
            netbios;
            parameter "id";
        }
        output {
            base64;
            print;
        }
    }
    server {
        output {
            base64;
            print;
        }
    }
}

http-stager {
    set uri_x86 "/a";
    set uri_x64 "/b";
    client {
        metadata {
            base64;
            header "Cookie";
        }
    }
    server {
        output {
            base64;
            print;
        }
    }
}
"""

    def _ingest(self, set_block: str) -> Profile:
        p = Profile()
        p.ingest(content=set_block + self._SKELETON)
        return p

    def test_default_host_stage_is_true(self):
        p = Profile()
        assert p.host_stage is True

    def test_default_sample_name_is_none(self):
        p = Profile()
        assert p.sample_name is None

    def test_host_stage_false_becomes_typed_bool(self):
        # The bug Tier 0 fixes: previously this stored the string "false"
        # which is truthy.
        p = self._ingest('set host_stage "false";\n')
        assert p.host_stage is False
        assert isinstance(p.host_stage, bool)

    def test_host_stage_true_becomes_typed_bool(self):
        p = self._ingest('set host_stage "true";\n')
        assert p.host_stage is True
        assert isinstance(p.host_stage, bool)

    def test_host_stage_garbage_value_is_falsy(self):
        # CS convention: anything not in the truthy literal set is False.
        p = self._ingest('set host_stage "definitely-not-true";\n')
        assert p.host_stage is False

    def test_sleeptime_normalized_to_int(self):
        p = self._ingest('set sleeptime "45000";\n')
        assert p.sleeptime == 45000  # noqa: PLR2004
        assert isinstance(p.sleeptime, int)

    def test_jitter_normalized_to_int(self):
        p = self._ingest('set jitter "25";\n')
        assert p.jitter == 25  # noqa: PLR2004
        assert isinstance(p.jitter, int)

    def test_sample_name_stored_verbatim(self):
        p = self._ingest('set sample_name "Operation Foo";\n')
        assert p.sample_name == "Operation Foo"

    def test_accepted_but_ignored_directive_logs_info(self, caplog):
        with caplog.at_level("INFO", logger="empire.server.common.malleable.profile"):
            self._ingest('set dns_idle "8.8.8.8";\n')
        messages = [r.getMessage() for r in caplog.records]
        info_logs = [
            m for m in messages if "dns_idle" in m and "does not act on it yet" in m
        ]
        assert info_logs, (
            f"expected INFO log for accepted-but-ignored key, saw: {messages}"
        )

    def test_accepted_but_ignored_directive_emits_no_warning(self, caplog):
        with caplog.at_level(
            "WARNING", logger="empire.server.common.malleable.profile"
        ):
            self._ingest('set dns_idle "8.8.8.8";\n')
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert warnings == [], (
            f"unexpected WARNINGs: {[r.getMessage() for r in warnings]}"
        )

    def test_unknown_directive_emits_warning(self, caplog):
        with caplog.at_level(
            "WARNING", logger="empire.server.common.malleable.profile"
        ):
            self._ingest('set totally_made_up_field "x";\n')
        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        assert any("totally_made_up_field" in w for w in warnings), (
            f"expected WARNING mentioning the unknown key, saw: {warnings}"
        )

    def test_roundtrip_through_serialize_preserves_host_stage(self):
        p = self._ingest('set host_stage "false";\n')
        roundtripped = Profile._deserialize(p._serialize())
        assert roundtripped.host_stage is False
        assert isinstance(roundtripped.host_stage, bool)

    def test_roundtrip_through_clone_preserves_sample_name(self):
        p = self._ingest('set sample_name "trial-run";\n')
        assert p._clone().sample_name == "trial-run"


class TestShippedProfilesAllowList:
    """Allow-list completeness check: every shipped profile in data/profiles
    must load with zero WARNING-level logs from the malleable parser. A new
    WARNING here means either (a) a shipped profile uses a CS field we forgot
    to add to _ACCEPTED_BUT_IGNORED_SET_KEYS, or (b) a profile genuinely has
    a typo that's worth surfacing — both deserve human review.
    """

    def test_no_warnings_loading_shipped_profiles(self, caplog):
        if not PROFILES_DIR.is_dir():
            pytest.skip("No bundled .profile fixtures found")

        shipped = sorted(PROFILES_DIR.rglob("*.profile"))
        if not shipped:
            pytest.skip("PROFILES_DIR exists but contains no .profile files")

        offenders: list[tuple[str, str]] = []
        with caplog.at_level(
            "WARNING", logger="empire.server.common.malleable.profile"
        ):
            for path in shipped:
                caplog.clear()
                p = Profile()
                try:
                    p.ingest(file=str(path))
                except Exception as exc:
                    # A profile that fails to *parse* is a different bug;
                    # the allow-list check is about runtime WARNING noise.
                    offenders.append((str(path), f"parse error: {exc}"))
                    continue
                for record in caplog.records:
                    if record.levelname == "WARNING":
                        offenders.append((str(path), record.getMessage()))

        assert offenders == [], (
            "shipped profiles produced parser warnings — either add the new key "
            "to _ACCEPTED_BUT_IGNORED_SET_KEYS in profile.py, or fix the profile:\n  "
            + "\n  ".join(f"{path}: {msg}" for path, msg in offenders)
        )

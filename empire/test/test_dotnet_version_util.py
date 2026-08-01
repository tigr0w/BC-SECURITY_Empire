from empire.server.utils.dotnet_version_util import (
    normalize_dotnet_version,
    parse_agent_dotnet_versions,
)


class TestNormalizeDotnetVersion:
    def test_net35_variants(self):
        assert normalize_dotnet_version("Net35") == "net35"
        assert normalize_dotnet_version("net35") == "net35"
        assert normalize_dotnet_version("NET35") == "net35"
        assert normalize_dotnet_version("3.5") == "net35"

    def test_net40_variants(self):
        assert normalize_dotnet_version("Net40") == "net40"
        assert normalize_dotnet_version("net40") == "net40"
        assert normalize_dotnet_version("NET40") == "net40"
        assert normalize_dotnet_version("4.0") == "net40"

    def test_net45_variants(self):
        assert normalize_dotnet_version("Net45") == "net45"
        assert normalize_dotnet_version("net45") == "net45"
        assert normalize_dotnet_version("NET45") == "net45"
        assert normalize_dotnet_version("4.5") == "net45"

    def test_net46_variants(self):
        assert normalize_dotnet_version("Net46") == "net46"
        assert normalize_dotnet_version("net46") == "net46"
        assert normalize_dotnet_version("NET46") == "net46"
        assert normalize_dotnet_version("4.6") == "net46"

    def test_net47_variants(self):
        assert normalize_dotnet_version("Net47") == "net47"
        assert normalize_dotnet_version("net47") == "net47"
        assert normalize_dotnet_version("NET47") == "net47"
        assert normalize_dotnet_version("4.7") == "net47"

    def test_net48_variants(self):
        assert normalize_dotnet_version("Net48") == "net48"
        assert normalize_dotnet_version("net48") == "net48"
        assert normalize_dotnet_version("NET48") == "net48"
        assert normalize_dotnet_version("4.8") == "net48"

    def test_empty_string_returns_none(self):
        assert normalize_dotnet_version("") is None

    def test_whitespace_only_returns_none(self):
        assert normalize_dotnet_version("   ") is None

    def test_none_returns_none(self):
        assert normalize_dotnet_version(None) is None

    def test_unknown_string_returns_none(self):
        assert normalize_dotnet_version("unknown") is None
        assert normalize_dotnet_version("net99") is None
        assert normalize_dotnet_version("9.9") is None
        assert normalize_dotnet_version("random") is None

    def test_with_whitespace(self):
        assert normalize_dotnet_version("  net45  ") == "net45"
        assert normalize_dotnet_version("  Net35  ") == "net35"
        assert normalize_dotnet_version("  4.5  ") == "net45"


class TestParseAgentDotnetVersions:
    def test_none_returns_empty(self):
        assert parse_agent_dotnet_versions(None) == frozenset()

    def test_empty_string_returns_empty(self):
        assert parse_agent_dotnet_versions("") == frozenset()

    def test_single_net48(self):
        assert parse_agent_dotnet_versions("net48") == frozenset({"net48"})

    def test_single_net35(self):
        assert parse_agent_dotnet_versions("net35") == frozenset({"net35"})

    def test_combined_net48_net35(self):
        assert parse_agent_dotnet_versions("net48,net35") == frozenset(
            {"net48", "net35"}
        )

    def test_case_insensitive(self):
        assert parse_agent_dotnet_versions("Net48,Net35") == frozenset(
            {"net48", "net35"}
        )

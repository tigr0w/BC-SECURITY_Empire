KNOWN_DOTNET_VERSIONS = {"net35", "net40", "net45", "net46", "net47", "net48"}

VERSION_ORDER = ["net35", "net40", "net45", "net46", "net47", "net48"]

CLR_2_VERSIONS: frozenset[str] = frozenset({"net35"})
CLR_4_VERSIONS: frozenset[str] = frozenset(
    {"net40", "net45", "net46", "net47", "net48"}
)

VERSION_MAPPING = {
    "3.5": "net35",
    "4.0": "net40",
    "4.5": "net45",
    "4.6": "net46",
    "4.7": "net47",
    "4.8": "net48",
}


def normalize_dotnet_version(raw: str | None) -> str | None:
    if raw is None:
        return None

    normalized = raw.strip().lower()

    if not normalized:
        return None

    if normalized in KNOWN_DOTNET_VERSIONS:
        return normalized

    if normalized.startswith("net"):
        candidate = normalized[3:].replace(".", "")
        if candidate.isdigit():
            candidate = "net" + candidate
            if candidate in KNOWN_DOTNET_VERSIONS:
                return candidate

    if normalized in VERSION_MAPPING:
        return VERSION_MAPPING[normalized]

    return None


def parse_agent_dotnet_versions(stored: str | None) -> frozenset[str]:
    """Parse a stored dotnet_version string into a set of available normalized versions.

    Handles both single values ("net48") and comma-separated values ("net48,net35").
    """
    if not stored:
        return frozenset()
    result = set()
    for part in stored.split(","):
        v = normalize_dotnet_version(part.strip())
        if v:
            result.add(v)
    return frozenset(result)

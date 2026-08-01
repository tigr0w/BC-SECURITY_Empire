import csv
import io
import logging

from empire.server.api.v2.credential.credential_dto import CredentialPostRequest
from empire.server.common.credential_parsers.base import coerce_str
from empire.server.common.credential_parsers.credtypes import PLAINTEXT

log = logging.getLogger(__name__)

TOOL_TAG = "session_gopher"

_USERNAME_KEYS = ("UserName", "Username", "User", "Login")
_PASSWORD_KEYS = ("Password", "Pass", "Credential")
_HOST_KEYS = ("Host", "Hostname", "Target", "HostName", "Server")
_SOURCE_KEYS = ("Source", "Session", "Application")


def _first(row: dict[str, str], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value:
            return value.strip()
    return ""


class SessionGopherParser:
    """Parses SessionGopher output exported as CSV. The companion YAML patches
    `script_end` to pipe through `ConvertTo-Csv -NoTypeInformation` so output
    is a single CSV table regardless of which Source plugin (WinSCP/PuTTY/
    RDP/FileZilla) produced a given row.
    """

    def parse(self, data, agent) -> list[CredentialPostRequest]:
        text = coerce_str(data).replace("\r\n", "\n")

        # SessionGopher may emit a "Gopher it!" banner above the CSV. Locate
        # the first line that looks like a CSV header and start there.
        lines = text.split("\n")
        start = None
        for i, line in enumerate(lines):
            lower = line.lower()
            if (
                "," in line
                and "password" in lower
                and any(k.lower() in lower for k in _USERNAME_KEYS)
            ):
                start = i
                break

        if start is None:
            return []

        agent_host = getattr(agent, "hostname", "") or ""
        agent_os = getattr(agent, "os_details", None)

        csv_body = "\n".join(lines[start:])
        reader = csv.DictReader(io.StringIO(csv_body))

        results: list[CredentialPostRequest] = []
        seen: set[tuple[str, str, str]] = set()

        for row in reader:
            password = _first(row, _PASSWORD_KEYS)
            username = _first(row, _USERNAME_KEYS)
            host = _first(row, _HOST_KEYS) or agent_host
            source = _first(row, _SOURCE_KEYS)

            # Skip rows where either identifier is missing — they would
            # collide under the (credtype, domain, username, password)
            # dedup key and clutter the DB.
            if not password or not username:
                continue

            # Some SessionGopher sources embed the domain in the username
            # field (`DOMAIN\user`).
            domain = ""
            if "\\" in username:
                domain, username = username.split("\\", 1)

            key = (username, password, host)
            if key in seen:
                continue
            seen.add(key)

            notes = f"{TOOL_TAG}:{source}" if source else TOOL_TAG

            results.append(
                CredentialPostRequest(
                    credtype=PLAINTEXT,
                    domain=domain,
                    username=username,
                    password=password,
                    host=host,
                    os=agent_os,
                    sid="",
                    notes=notes,
                )
            )

        return results

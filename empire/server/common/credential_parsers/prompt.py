import logging

from empire.server.api.v2.credential.credential_dto import CredentialPostRequest
from empire.server.common.credential_parsers.base import coerce_bytes
from empire.server.common.credential_parsers.credtypes import PLAINTEXT

log = logging.getLogger(__name__)

TOOL_TAG = "prompt"


class PromptParser:
    """Captures prompt-driven credential output from `powershell/collection/prompt`
    and the macOS `python/collection/prompt` module. Both emit on a single line.
    """

    def parse(self, data, agent) -> list[CredentialPostRequest]:
        data = coerce_bytes(data)
        first_line = data.split(b"\n", 1)[0]

        if first_line.startswith(b"[+] Prompted credentials:"):
            return self._parse_powershell_prompt(first_line, agent)

        if b"text returned:" in first_line:
            return self._parse_mac_prompt(first_line, agent)

        return []

    def _parse_powershell_prompt(
        self, line: bytes, agent
    ) -> list[CredentialPostRequest]:
        parts = line.split(b"->")
        if len(parts) != 2:  # noqa: PLR2004
            log.error("Error in parsing prompted credential output.")
            return []

        try:
            user_raw, password_raw = parts[1].split(b":", 1)
        except ValueError:
            log.error("Error in parsing prompted credential output.")
            return []

        username = user_raw.strip().decode("UTF-8", errors="replace")
        password = password_raw.strip().decode("UTF-8", errors="replace")

        if "\\" in username:
            domain, username = username.split("\\", 1)
            domain = domain.strip()
            username = username.strip()
        else:
            domain = ""

        return [
            CredentialPostRequest(
                credtype=PLAINTEXT,
                domain=domain,
                username=username,
                password=password,
                host=getattr(agent, "hostname", "") or "",
                os=getattr(agent, "os_details", None),
                sid="",
                notes=TOOL_TAG,
            )
        ]

    def _parse_mac_prompt(self, line: bytes, agent) -> list[CredentialPostRequest]:
        parts = line.split(b"text returned:")
        if len(parts) < 2:  # noqa: PLR2004
            return []
        password = parts[-1].strip().decode("UTF-8", errors="replace")
        if not password:
            return []
        return [
            CredentialPostRequest(
                credtype=PLAINTEXT,
                domain="",
                username="",
                password=password,
                host=getattr(agent, "hostname", "") or "",
                os=getattr(agent, "os_details", None),
                sid="",
                notes=TOOL_TAG,
            )
        ]

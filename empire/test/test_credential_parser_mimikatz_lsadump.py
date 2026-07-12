"""Tests for the MimikatzParser lsadump krbtgt and dcsync fallback branches,
which the existing sekurlsa-focused credential-parser tests don't reach.
"""

from empire.server.common.credential_parsers.credtypes import HASH
from empire.server.common.credential_parsers.mimikatz import MimikatzParser

# lsadump::lsa /inject style output containing a krbtgt account. No sekurlsa
# credential regions, so the parser falls back to the krbtgt hashdump path.
KRBTGT_SAMPLE = b"\n".join(
    [
        b"Hostname: DC01.corp.local / S-1-5-21-9-9-9",
        b"",
        b"mimikatz # lsadump::lsa /inject",
        b"",
        b"filler",
        b"filler",
        b"filler",
        b"filler",
        b"Domain : CORP / S-1-5-21-9-9-9",  # index 8
        b"",
        b"RID  : 000001f6 (502)",
        b"User : krbtgt",  # index 11
        b"",
        b"  Hash NTLM: aad3b435b51404eeaad3b435b51404ee",  # index 13 (11 + 2)
    ]
)

# lsadump::dcsync output with a SAM account block.
DCSYNC_SAMPLE = b"\n".join(
    [
        b"Hostname: DC01.corp.local / S-1-5-21-9-9-9",
        b"",
        b"mimikatz # lsadump::dcsync /user:Administrator",
        b"[DC] 'corp.local' will be the domain",
        b"[DC] 'DC01.corp.local' will be the DC server",
        b"[DC] 'Administrator' will be the user account",
        b"",
        b"** SAM ACCOUNT **",
        b"",
        b"SAM Username         : Administrator",
        b"Object Security ID   : S-1-5-21-9-9-9-500",
        b"",
        b"Credentials:",
        b"  Hash NTLM: 31d6cfe0d16ae931b73c59d7e0c089c0",
    ]
)


def test_mimikatz_lsadump_extracts_krbtgt_hash(agent):
    creds = MimikatzParser().parse(KRBTGT_SAMPLE, agent)

    assert len(creds) == 1
    cred = creds[0]
    assert cred.credtype == HASH
    assert cred.username == "krbtgt"
    assert cred.password == "aad3b435b51404eeaad3b435b51404ee"
    # host_domain from the Hostname header takes precedence over "CORP".
    assert cred.domain == "corp.local"
    assert cred.sid == "S-1-5-21-9-9-9"


def test_mimikatz_dcsync_extracts_sam_account(agent):
    creds = MimikatzParser().parse(DCSYNC_SAMPLE, agent)

    assert len(creds) == 1
    cred = creds[0]
    assert cred.credtype == HASH
    assert cred.username == "Administrator"
    assert cred.password == "31d6cfe0d16ae931b73c59d7e0c089c0"
    assert cred.domain == "corp.local"
    assert cred.host == "DC01"
    # The RID is stripped from the Object Security ID.
    assert cred.sid == "S-1-5-21-9-9-9"

"""Unit tests for empire.server.common.credential_parsers.

Each parser is tested against a small captured-output fixture baked into the
test; fixtures purposely live inline so regressions surface in diff review
alongside the parser change. Only the agent's `hostname` / `os_details`
attributes are used by parsers, so a trivial namespace object is sufficient.
"""

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from empire.server.common import credential_parsers
from empire.server.common.credential_parsers.credtypes import (
    DCC2,
    DPAPI_MASTERKEY,
    DPAPI_SYSTEM_KEY,
    DPAPI_VAULT_CRED,
    HASH,
    KRB_SESSION_KEY,
    KRB_TICKET,
    KRBASREP,
    KRBTGS,
    NETNTLMV1,
    NETNTLMV2,
    PLAINTEXT,
)
from empire.server.common.credential_parsers.internal_monologue import (
    InternalMonologueParser,
)
from empire.server.common.credential_parsers.inveigh import InveighParser
from empire.server.common.credential_parsers.kerberoast import KerberoastParser
from empire.server.common.credential_parsers.mimikatz import MimikatzParser
from empire.server.common.credential_parsers.ntlmextract import NtlmExtractParser
from empire.server.common.credential_parsers.prompt import PromptParser
from empire.server.common.credential_parsers.pwdump_hashes import (
    MACHINE_ACCOUNT_TAG,
    PwdumpHashesParser,
)
from empire.server.common.credential_parsers.rubeus import RubeusParser
from empire.server.common.credential_parsers.session_gopher import SessionGopherParser
from empire.server.common.credential_parsers.sharp_dpapi import SharpDpapiParser
from empire.server.common.credential_parsers.sharpsecdump import SharpSecDumpParser
from empire.server.common.credential_parsers.tgtdelegation import TgtDelegationParser
from empire.server.core.module_models import EmpireModule


@pytest.fixture
def agent():
    return SimpleNamespace(hostname="WIN-AGENT", os_details="Windows 10 x64")


# ---------- Registry ----------------------------------------------------------


def test_registry_contains_all_parsers():
    # Iterate the registry so new parser additions are checked automatically.
    for name in credential_parsers.registered_parser_names():
        assert credential_parsers.get_parser(name) is not None, name
    # Lock in the set of parser names the YAMLs reference — catches accidental
    # renames that would silently unwire modules from ingestion.
    expected = {
        "mimikatz",
        "prompt",
        "kerberoast",
        "rubeus",
        "pwdump_hashes",
        "sharp_dpapi",
        "session_gopher",
        "internal_monologue",
        "sharpsecdump",
        "ntlmextract",
        "tgtdelegation",
        "inveigh",
    }
    assert expected <= set(credential_parsers.registered_parser_names())


def test_get_parser_unknown_returns_none():
    assert credential_parsers.get_parser("does_not_exist") is None
    assert credential_parsers.get_parser(None) is None


def test_credtype_constants_have_stable_values():
    """Out-of-tree plugins, hashcat-mode-detection logic, Starkiller
    filters, and migration scripts all key on the literal credtype
    string. Pin every wire value so a rename here triggers a test
    failure rather than silently breaking downstream consumers.
    """
    assert HASH == "hash"
    assert PLAINTEXT == "plaintext"
    assert NETNTLMV1 == "netntlmv1"
    assert NETNTLMV2 == "netntlmv2"
    assert DCC2 == "dcc2"
    assert KRBTGS == "krbtgs"
    assert KRBASREP == "krbasrep"
    assert KRB_TICKET == "krb_ticket"
    assert KRB_SESSION_KEY == "krb_session_key"
    assert DPAPI_MASTERKEY == "dpapi_masterkey"
    assert DPAPI_SYSTEM_KEY == "dpapi_system_key"
    assert DPAPI_VAULT_CRED == "dpapi_vault_cred"


def test_empire_module_rejects_unknown_credential_parser():
    """The pydantic validator on EmpireModule surfaces YAML typos at
    module-load time rather than at the first credential-producing task.
    """
    base = {
        "id": "test_mod",
        "name": "test_mod",
        "language": "powershell",
    }
    EmpireModule(**base)
    EmpireModule(**base, credential_parser="mimikatz")

    with pytest.raises(ValidationError, match="unknown credential_parser"):
        EmpireModule(**base, credential_parser="not_a_real_parser")


def test_detect_by_prefix_mimikatz():
    parser = credential_parsers.detect_by_prefix(b"Hostname: WIN-DC/S-1-5-21\n...")
    assert isinstance(parser, MimikatzParser)


def test_detect_by_prefix_prompt_powershell():
    assert isinstance(
        credential_parsers.detect_by_prefix(b"[+] Prompted credentials: foo->bar:baz"),
        PromptParser,
    )


def test_detect_by_prefix_prompt_mac():
    assert isinstance(
        credential_parsers.detect_by_prefix(
            b"button returned:OK, text returned:secret"
        ),
        PromptParser,
    )


def test_detect_by_prefix_unknown():
    assert credential_parsers.detect_by_prefix(b"random output") is None


# ---------- Mimikatz ----------------------------------------------------------


MIMIKATZ_SAMPLE = b"""Hostname: WIN-DC.example.local/S-1-5-21-111-222-333

Authentication Id : 0 ; 12345 (00000000:00001234)
Session           : Interactive from 1
User Name         : jdoe
Domain            : EXAMPLE
Logon Server      : DC01
Logon Time        : 1/1/2024 10:00:00
SID               : S-1-5-21-111-222-333-1001
\tmsv :
\t [00000003] Primary
\t * Username : jdoe
\t * Domain   : EXAMPLE
\t * NTLM     : aad3b435b51404eeaad3b435b51404ee
\t tspkg :
\t * Username : jdoe
\t * Domain   : EXAMPLE
\t * Password : SuperSecret!
\t wdigest :
\t * Username : (null)
\t * Domain   : (null)
\t * Password : (null)
\t kerberos :
\t * Username : jdoe
\t * Domain   : EXAMPLE
\t * Password : (null)
\t ssp :
\t credman :

Authentication Id : 0 ; 999
"""


def test_mimikatz_parses_plaintext_and_hash(agent):
    creds = MimikatzParser().parse(MIMIKATZ_SAMPLE, agent)

    users = {(c.credtype, c.username, c.password) for c in creds}
    assert (HASH, "jdoe", "aad3b435b51404eeaad3b435b51404ee") in users
    assert (PLAINTEXT, "jdoe", "SuperSecret!") in users
    assert all(c.host == "WIN-DC" for c in creds)
    assert all(c.os == "Windows 10 x64" for c in creds)
    assert all(c.notes == "mimikatz" for c in creds)


def test_mimikatz_skips_machine_account_plaintext(agent):
    data = MIMIKATZ_SAMPLE.replace(b"Username : jdoe", b"Username : DC01$")
    creds = MimikatzParser().parse(data, agent)
    assert not any(c.credtype == PLAINTEXT and c.username == "DC01$" for c in creds)


def test_mimikatz_empty_for_non_matching_output(agent):
    assert MimikatzParser().parse(b"totally unrelated output", agent) == []


# ---------- Prompt ------------------------------------------------------------


def test_prompt_powershell_domain_user(agent):
    data = b"[+] Prompted credentials: foo-> CORP\\jdoe : SecretPw!"
    creds = PromptParser().parse(data, agent)
    assert len(creds) == 1
    assert creds[0].credtype == PLAINTEXT
    assert creds[0].domain == "CORP"
    assert creds[0].username == "jdoe"
    assert creds[0].password == "SecretPw!"
    assert creds[0].host == "WIN-AGENT"


def test_prompt_powershell_no_domain(agent):
    data = b"[+] Prompted credentials: foo-> jdoe : hunter2"
    creds = PromptParser().parse(data, agent)
    assert len(creds) == 1
    assert creds[0].domain == ""
    assert creds[0].username == "jdoe"
    assert creds[0].password == "hunter2"


def test_prompt_mac_text_returned(agent):
    data = b"button returned:OK, text returned:mypassword"
    creds = PromptParser().parse(data, agent)
    assert len(creds) == 1
    assert creds[0].credtype == PLAINTEXT
    assert creds[0].password == "mypassword"
    assert creds[0].username == ""


# ---------- Kerberoast --------------------------------------------------------


KERBEROAST_RUBEUS_SAMPLE = """
[*] SamAccountName         : sqlservice
[*] DistinguishedName      : CN=sqlservice,CN=Users,DC=example,DC=local
[*] ServicePrincipalName   : MSSQLSvc/sql1.example.local:1433
[*] PwdLastSet             : 2024-01-15 10:22:44

$krb5tgs$23$*sqlservice$example.local$MSSQLSvc/sql1.example.local:1433*$DEADBEEF
    CAFEBABE0102030405060708
    090A0B0C0D0E0F1011121314

[*] SamAccountName         : backup-svc

$krb5tgs$23$*backup-svc$example.local$host/backup.example.local*$AAAA1111BBBB2222
"""


def test_kerberoast_extracts_all_spns(agent):
    creds = KerberoastParser().parse(KERBEROAST_RUBEUS_SAMPLE, agent)
    assert len(creds) == 2  # noqa: PLR2004
    assert {c.username for c in creds} == {"sqlservice", "backup-svc"}
    assert {c.domain for c in creds} == {"example.local"}
    assert all(c.credtype == KRBTGS for c in creds)
    assert all(c.notes == "kerberoast" for c in creds)

    sql = next(c for c in creds if c.username == "sqlservice")
    # Wrapped continuation hex should be re-assembled onto a single line.
    assert "\n" not in sql.password
    assert sql.password.endswith(
        "DEADBEEFCAFEBABE0102030405060708090A0B0C0D0E0F1011121314"
    )
    assert sql.password.startswith(
        "$krb5tgs$23$*sqlservice$example.local$MSSQLSvc/sql1.example.local:1433*$"
    )


def test_kerberoast_returns_empty_without_token(agent):
    assert KerberoastParser().parse(b"nothing to see here", agent) == []


# ---------- Pwdump hashes -----------------------------------------------------


PWDUMP_SAMPLE = """
Administrator:500:aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0:::
jdoe:1001:aad3b435b51404eeaad3b435b51404ee:0cb6948805f797bf2a82807973b89537:::
WIN10$:1002:aad3b435b51404eeaad3b435b51404ee:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:::
Guest:501:NO PASSWORD*********************:NO PASSWORD*********************:::
"""


def test_pwdump_parses_users_and_machine_accounts(agent):
    creds = PwdumpHashesParser().parse(PWDUMP_SAMPLE, agent)
    names = {c.username: c for c in creds}

    assert "Administrator" in names
    assert names["Administrator"].credtype == HASH
    assert names["Administrator"].password == "31d6cfe0d16ae931b73c59d7e0c089c0"
    assert names["Administrator"].notes == "pwdump_hashes"

    assert "WIN10$" in names
    assert MACHINE_ACCOUNT_TAG in names["WIN10$"].notes
    assert names["WIN10$"].credtype == HASH


def test_pwdump_ignores_non_matching_lines(agent):
    assert PwdumpHashesParser().parse(b"prose preamble\nno hashes here", agent) == []


# ---------- SharpDPAPI --------------------------------------------------------


SHARP_DPAPI_MASTERKEYS = """
[*] Triage User Masterkeys

[*] Master key file      : C:\\Users\\admin\\AppData\\Roaming\\Microsoft\\Protect\\S-1-5-21-111-222-333-1001\\a1b2c3d4-0000-0000-0000-000000000001
  [*] guidMasterKey    : {a1b2c3d4-0000-0000-0000-000000000001}
  [*] SHA1 MasterKey   : ffffffffffffffffffffffffffffffffffffffff

[*] Master key file      : C:\\Users\\admin\\AppData\\Roaming\\Microsoft\\Protect\\S-1-5-21-111-222-333-1001\\b1b2c3d4-0000-0000-0000-000000000002
  [*] guidMasterKey    : {b1b2c3d4-0000-0000-0000-000000000002}
  [!] Masterkey decryption failed
"""


SHARP_DPAPI_VAULT = """
[*] Triage Chrome Credentials

--- Chrome Credential (User: admin) ---
URL        : https://mail.google.com/
Username   : attacker@gmail.com
Password   : hunter2

--- Chrome Credential (User: admin) ---
URL        : https://github.com/
Username   : attacker
Password   : another!pass
"""


def test_sharp_dpapi_masterkeys_emits_only_successful_decryptions(agent):
    creds = SharpDpapiParser().parse(SHARP_DPAPI_MASTERKEYS, agent)
    masterkeys = [c for c in creds if c.credtype == DPAPI_MASTERKEY]

    assert len(masterkeys) == 1
    assert masterkeys[0].username == "a1b2c3d4-0000-0000-0000-000000000001"
    assert masterkeys[0].password == (
        "a1b2c3d4-0000-0000-0000-000000000001:ffffffffffffffffffffffffffffffffffffffff"
    )
    assert masterkeys[0].notes == "sharp_dpapi"


def test_sharp_dpapi_vault_extracts_url_user_password(agent):
    creds = SharpDpapiParser().parse(SHARP_DPAPI_VAULT, agent)
    vault_creds = [c for c in creds if c.credtype == DPAPI_VAULT_CRED]

    assert len(vault_creds) == 2  # noqa: PLR2004
    payloads = [json.loads(c.password) for c in vault_creds]
    urls = {p["url"] for p in payloads}
    assert urls == {"https://mail.google.com/", "https://github.com/"}
    assert {p["username"] for p in payloads} == {"attacker@gmail.com", "attacker"}


# ---------- SessionGopher -----------------------------------------------------


SESSION_GOPHER_CSV = """Gopher it!

"Source","Host","UserName","Password"
"WinSCP","server1.corp.local","CORP\\jdoe","WinScpPass"
"PuTTY","10.0.0.5","root","RootPuTTy!"
"""


def test_session_gopher_parses_csv_rows(agent):
    creds = SessionGopherParser().parse(SESSION_GOPHER_CSV, agent)

    assert len(creds) == 2  # noqa: PLR2004
    winscp = next(c for c in creds if c.host == "server1.corp.local")
    assert winscp.credtype == PLAINTEXT
    assert winscp.domain == "CORP"
    assert winscp.username == "jdoe"
    assert winscp.password == "WinScpPass"
    assert winscp.notes == "session_gopher:WinSCP"

    putty = next(c for c in creds if c.host == "10.0.0.5")
    assert putty.username == "root"
    assert putty.notes == "session_gopher:PuTTY"


def test_session_gopher_ignores_preamble(agent):
    # No CSV header present → no rows.
    assert SessionGopherParser().parse(b"Gopher it!\nNothing else\n", agent) == []


# ---------- Rubeus ------------------------------------------------------------


# Captured from `Rubeus {"Command": "asktgt /user:m.torres /password:... /domain:cyberdef"}`
# — the full default wrapped base64 body and metadata block.
RUBEUS_ASKTGT_SAMPLE = """
   ______        _
  (_____ \\      | |
   _____) )_   _| |__  _____ _   _  ___
  |  __  /| | | |  _ \\| ___ | | | |/___)
  | |  \\ \\| |_| | |_) ) ____| |_| |___ |
  |_|   |_|____/|____/|_____)____/(___/

  v2.3.2

[*] Action: Ask TGT

[*] Using rc4_hmac hash: EEB5FD1A992838D0D4894418D6BB44FB
[*] Building AS-REQ (w/ preauth) for: 'cyberdef\\m.torres'
[*] Using domain controller: 10.2.10.10:88
[+] TGT request successful!
[*] base64(ticket.kirbi):

      doIFejCCBXagAwIBBaEDAgEWooIEkzCCBI9hggSLMIIEh6ADAgEFoQ4bDENZQkVSREVGLkxBQqIdMBug
      AwIBAqEUMBIbBmtyYnRndBsIY3liZXJkZWajggRPMIIES6ADAgESoQMCAQKiggQ9BIIEORD9iotXiRjX
      H6jM8umBQJ50Zl45HXBP/eoaQL/qNjN7mtANM5EyWEuPEtOxbeVrEJj4UH+xHjH6AkPbAx3h9fMEsJ1e

  ServiceName              :  krbtgt/cyberdef
  ServiceRealm             :  CYBERDEF.LAB
  UserName                 :  m.torres (NT_PRINCIPAL)
  UserRealm                :  CYBERDEF.LAB
  StartTime                :  4/22/2026 1:12:43 PM
  EndTime                  :  4/22/2026 11:12:43 PM
  RenewTill                :  4/29/2026 1:12:43 PM
  Flags                    :  name_canonicalize, pre_authent, initial, renewable, forwardable
  KeyType                  :  rc4_hmac
  Base64(key)              :  lv0970NGUZwGumWhU32aZQ==
  ASREP (key)              :  EEB5FD1A992838D0D4894418D6BB44FB
"""


def test_rubeus_asktgt_emits_ticket_and_ntlm_hash(agent):
    creds = RubeusParser().parse(RUBEUS_ASKTGT_SAMPLE, agent)

    tickets = [c for c in creds if c.credtype == KRB_TICKET]
    hashes = [c for c in creds if c.credtype == HASH]

    assert len(tickets) == 1
    t = tickets[0]
    assert t.username == "m.torres"
    assert t.domain == "CYBERDEF.LAB"
    assert "\n" not in t.password
    # Single-line reconstruction should preserve all base64 chunks in order.
    assert t.password.startswith("doIFejCCBXagAwIBBaEDAgEWooIEkzCCBI9hggSLMIIEh6")
    assert t.password.endswith("EJj4UH+xHjH6AkPbAx3h9fMEsJ1e")
    assert "rubeus" in (t.notes or "")

    assert len(hashes) == 1
    h = hashes[0]
    assert h.username == "m.torres"
    assert h.domain == "CYBERDEF.LAB"
    assert h.password == "eeb5fd1a992838d0d4894418d6bb44fb"
    assert "rubeus" in (h.notes or "")


# Captured from `Rubeus {"Command": "dump"}` on a live agent. `dump` differs
# from asktgt/asktgs in three ways this fixture preserves verbatim: the anchor
# is `Base64EncodedTicket :` rather than `base64(ticket.kirbi):`, the metadata
# block sits ABOVE that anchor rather than below it, and tickets are grouped
# under logon-session headers carrying `UserSID`. The `WINHOSTTHREE$` ticket
# also keeps the mid-value line wrap the agent transport introduced.
RUBEUS_DUMP_SAMPLE = """
   ______        _
  (_____ \\      | |
   _____) )_   _| |__  _____ _   _  ___

  v2.3.2


Action: Dump Kerberos Ticket Data (All Users)

[*] Current LUID    : 0x86263

  UserName                 : LEO_MADDEN
  Domain                   : ASGARD
  LogonId                  : 0x86485
  UserSID                  : S-1-5-21-3981194929-2845007435-449810890-4550
  AuthenticationPackage    : Negotiate
  LogonType                : RemoteInteractive
  LogonServerDNSDomain     : ASGARD.CORP
  UserPrincipalName        : LEO_MADDEN@asgard.corp


    ServiceName              :  krbtgt/ASGARD.CORP
    ServiceRealm             :  ASGARD.CORP
    UserName                 :  LEO_MADDEN (NT_PRINCIPAL)
    UserRealm                :  ASGARD.CORP
    StartTime                :  8/20/2026 6:34:34 PM
    EndTime                  :  8/21/2026 4:34:34 AM
    RenewTill                :  8/27/2026 6:34:34 PM
    Flags                    :  name_canonicalize, pre_authent, initial, renewable, forwardable
    KeyType                  :  aes256_cts_hmac_sha1
    Base64(key)              :  bsntG2x5Umfv9OIxCZrFHgkblbRK2P58kVqZSc5An/I=
    Base64EncodedTicket   :

      doIFwDCCBbygAwIBBaEDAgEWooIExjCCBMJhggS+MIIEuqADAgEFoQ0bC0FTR0FSRC5DT1JQ
      oiAwHqADAgECoRcwFRsGa3JidGd0GwtBU0dBUkQuQ09SUKOCBIAwggR8oAMCARKhAwIBAqKC


[*] Current LUID    : 0x3e7

  UserName                 : WINHOSTTHREE$
  Domain                   : ASGARD
  LogonId                  : 0x3e7
  UserSID                  : S-1-5-18
  AuthenticationPackage    : Negotiate


    ServiceName              :  GC/dc.asgard.corp/asgard.corp
    ServiceRealm             :  ASGARD.CORP
    UserName                 :  WINHOSTTHREE$ (NT_PRINC
IPAL)
    UserRealm                :  ASGARD.CORP
    StartTime                :  8/20/2026 6:36:18 PM
    EndTime                  :  8/21/2026 4:33:59 AM
    RenewTill                :  8/27/2026 6:33:59 PM
    Flags                    :  name_canonicalize, ok_as_delegate, pre_authent, renewable, forwardable
    KeyType                  :  aes256_cts_hmac_sha1
    Base64(key)              :  AcH70brAsMtQ2wkJ7Egev2EkLEItfs5IDnM6NM7YdB8=
    Base64EncodedTicket   :

      doIGRDCCBkCgAwIBBaEDAgEWooIFVzCCBVNhggVPMIIFS6ADAgEFoQ0bC0FTR0FSRC5DT1JQ
      QVNHQVJELkNPUlA=
"""


def test_rubeus_dump_extracts_tickets_above_anchor(agent):
    """`dump` prints metadata ABOVE `Base64EncodedTicket :`. Reading it in the
    kirbi direction (below) silently attributed each ticket to the *next*
    ticket's fields, so pin the pairing, not just the count.
    """
    creds = RubeusParser().parse(RUBEUS_DUMP_SAMPLE, agent)
    tickets = [c for c in creds if c.credtype == KRB_TICKET]

    # The list comparison pins both the count and the ordered pairing.
    assert [t.username for t in tickets] == ["LEO_MADDEN", "WINHOSTTHREE$"]
    assert {t.domain for t in tickets} == {"ASGARD.CORP"}

    tgt = tickets[0]
    assert tgt.password.startswith("doIFwDCCBbygAwIBBaEDAgEWooIExjCCBMJhggS+")
    assert tgt.password.endswith(
        "oiAwHqADAgECoRcwFRsGa3JidGd0GwtBU0dBUkQuQ09SUKOCBIAwggR8oAMCARKhAwIBAqKC"
    )
    assert "\n" not in tgt.password
    # Bodies must not bleed into each other across ticket boundaries.
    assert tickets[1].password.startswith(
        "doIGRDCCBkCgAwIBBaEDAgEWooIFVzCCBVNhggVPMIIFS6"
    )


def test_rubeus_dump_tags_subcommand_from_anchor(agent):
    """The Flags heuristic would call the TGT here `asktgt` (it carries
    `initial`). The anchor already tells us it came from `dump`, so the
    notes must say so — operators filter on that tag.
    """
    creds = RubeusParser().parse(RUBEUS_DUMP_SAMPLE, agent)
    # Compare the tag itself, not a substring — `notes` carries a trailing
    # service name, and `in` would also accept `rubeus:dump-anything`.
    assert all((c.notes or "").split(" ")[0] == "rubeus:dump" for c in creds)


def test_rubeus_dump_carries_logon_session_sid(agent):
    """Only `dump` exposes the owning `UserSID`; each ticket must inherit the
    SID of the session header it appears under, not the first one seen.
    """
    creds = RubeusParser().parse(RUBEUS_DUMP_SAMPLE, agent)
    by_user = {c.username: c.sid for c in creds}
    assert by_user["LEO_MADDEN"] == "S-1-5-21-3981194929-2845007435-449810890-4550"
    assert by_user["WINHOSTTHREE$"] == "S-1-5-18"


def test_rubeus_dump_rejoins_transport_wrapped_field(agent):
    """The agent transport hard-wraps long lines mid-value. The orphan tail
    (`IPAL)`) otherwise reads as a block boundary and truncates the metadata,
    dropping the username entirely.
    """
    creds = RubeusParser().parse(RUBEUS_DUMP_SAMPLE, agent)
    usernames = [c.username for c in creds]
    assert "WINHOSTTHREE$" in usernames
    assert not any(u == "" for u in usernames)
    # The `(NT_PRINCIPAL)` annotation must still be stripped after rejoining.
    assert not any("NT_PRINC" in u for u in usernames)


def test_rubeus_dump_extracts_session_keys(agent):
    """Every ticket carries a `Base64(key)` session key. It is stored with its
    encryption type prefixed, because a bare key is ambiguous between
    rc4_hmac and the aes variants and unusable without that.
    """
    creds = RubeusParser().parse(RUBEUS_DUMP_SAMPLE, agent)
    keys = [c for c in creds if c.credtype == KRB_SESSION_KEY]

    assert [k.username for k in keys] == ["LEO_MADDEN", "WINHOSTTHREE$"]
    assert keys[0].password == (
        "aes256_cts_hmac_sha1:bsntG2x5Umfv9OIxCZrFHgkblbRK2P58kVqZSc5An/I="
    )
    assert keys[1].password == (
        "aes256_cts_hmac_sha1:AcH70brAsMtQ2wkJ7Egev2EkLEItfs5IDnM6NM7YdB8="
    )


def test_rubeus_session_key_pairs_with_ticket_via_notes(agent):
    """One logon session holds many tickets, so a key is only actionable if
    you can tell which ticket it decrypts. The service name in `notes` is
    what joins the two rows back together.
    """
    creds = RubeusParser().parse(RUBEUS_DUMP_SAMPLE, agent)
    by_type = {}
    for c in creds:
        by_type.setdefault(c.credtype, []).append(c)

    for ticket, key in zip(by_type[KRB_TICKET], by_type[KRB_SESSION_KEY], strict=True):
        assert ticket.notes == key.notes
    assert by_type[KRB_SESSION_KEY][0].notes == "rubeus:dump krbtgt/ASGARD.CORP"
    assert (
        by_type[KRB_SESSION_KEY][1].notes == "rubeus:dump GC/dc.asgard.corp/asgard.corp"
    )


# Real `dump` groups several tickets under one logon-session header, and the
# first ticket abuts that header with no blank line between them.
RUBEUS_DUMP_SHARED_SESSION_SAMPLE = """
[*] Current LUID    : 0x86263

  UserName                 : LEO_MADDEN
  Domain                   : ASGARD
  LogonId                  : 0x86485
  UserSID                  : S-1-5-21-3981194929-2845007435-449810890-4550
  AuthenticationPackage    : Negotiate
    ServiceName              :  krbtgt/ASGARD.CORP
    ServiceRealm             :  ASGARD.CORP
    UserName                 :  leo_madden (NT_PRINCIPAL)
    UserRealm                :  ASGARD.CORP
    KeyType                  :  aes256_cts_hmac_sha1
    Base64(key)              :  bsntG2x5Umfv9OIxCZrFHgkblbRK2P58kVqZSc5An/I=
    Base64EncodedTicket   :

      doIFwDCCBbygAwIBBaEDAgEWooIExjCCBMJhggS+MIIEuqADAgEFoQ0bC0FTR0FSRC5DT1JQ

    ServiceName              :  cifs/fs01.asgard.corp
    ServiceRealm             :  ASGARD.CORP
    UserName                 :  leo_madden (NT_PRINCIPAL)
    UserRealm                :  ASGARD.CORP
    KeyType                  :  aes256_cts_hmac_sha1
    Base64(key)              :  Zm9vYmFyMTIzNDU2Nzg5MGFiY2RlZmdoaWprbG1ub3A=
    Base64EncodedTicket   :

      doIGRDCCBkCgAwIBBaEDAgEWooIFVzCCBVNhggVPMIIFS6ADAgEFoQ0bC0FTR0FSRC5DT1JQ

    ServiceName              :  LDAP/dc01.asgard.corp
    ServiceRealm             :  ASGARD.CORP
    UserName                 :  leo_madden (NT_PRINCIPAL)
    UserRealm                :  ASGARD.CORP
    KeyType                  :  rc4_hmac
    Base64(key)              :  T1RIRVJLRVkxMjM0NTY3OA==
    Base64EncodedTicket   :

      doIHRDCCB0CgAwIBBaEDAgEWooIGVzCCBlNhggZPMIIGS6ADAgEFoQ0bC0FTR0FSRC5DT1JQ
"""


def test_rubeus_dump_ticket_abutting_header_keeps_own_username(agent):
    """The first ticket under a logon-session header has no blank line above
    it, so the backward walk runs straight into the header. The boundary stop
    cannot help there — only "nearest key wins" keeps the ticket's own
    `UserName` from being shadowed by the session owner's.
    """
    creds = RubeusParser().parse(RUBEUS_DUMP_SHARED_SESSION_SAMPLE, agent)
    tickets = [c for c in creds if c.credtype == KRB_TICKET]

    # The session header says `LEO_MADDEN`; every ticket says `leo_madden`.
    assert [t.username for t in tickets] == ["leo_madden"] * 3


def test_rubeus_dump_multiple_tickets_share_one_session_header(agent):
    """One session holds many tickets. Each must keep its own service name
    and inherit the single header's SID, rather than collapsing into one
    credential or picking up a neighbour's fields.
    """
    creds = RubeusParser().parse(RUBEUS_DUMP_SHARED_SESSION_SAMPLE, agent)
    tickets = [c for c in creds if c.credtype == KRB_TICKET]

    assert [t.notes for t in tickets] == [
        "rubeus:dump krbtgt/ASGARD.CORP",
        "rubeus:dump cifs/fs01.asgard.corp",
        "rubeus:dump LDAP/dc01.asgard.corp",
    ]
    assert {t.sid for t in tickets} == {"S-1-5-21-3981194929-2845007435-449810890-4550"}


def test_rubeus_asktgt_extracts_session_key(agent):
    """The kirbi-style layout carries `Base64(key)` too — the session key is
    not a dump-only field, so both metadata directions must yield it.
    """
    creds = RubeusParser().parse(RUBEUS_ASKTGT_SAMPLE, agent)
    keys = [c for c in creds if c.credtype == KRB_SESSION_KEY]

    assert len(keys) == 1
    assert keys[0].password == "rc4_hmac:lv0970NGUZwGumWhU32aZQ=="
    assert keys[0].username == "m.torres"
    assert keys[0].domain == "CYBERDEF.LAB"


RUBEUS_DUMP_NO_KEY_SAMPLE = """
    ServiceName              :  krbtgt/ASGARD.CORP
    UserName                 :  LEO_MADDEN (NT_PRINCIPAL)
    UserRealm                :  ASGARD.CORP
    KeyType                  :  aes256_cts_hmac_sha1
    Base64(key)              :
    Base64EncodedTicket   :

      doIFwDCCBbygAwIBBaEDAgEWooIExjCCBMJhggS+MIIEuqADAgEFoQ0bC0FTR0FSRC5DT1JQ
"""


def test_rubeus_skips_missing_session_key(agent):
    """Rubeus prints an empty `Base64(key)` when it cannot read the key.
    Storing an empty-password credential would be noise the operator has to
    triage, so the ticket is kept and the key row is dropped.
    """
    creds = RubeusParser().parse(RUBEUS_DUMP_NO_KEY_SAMPLE, agent)

    assert [c.credtype for c in creds] == [KRB_TICKET]


RUBEUS_DUMP_ODD_KEYTYPE_SAMPLE = """
    ServiceName              :  krbtgt/ASGARD.CORP
    UserName                 :  LEO_MADDEN (NT_PRINCIPAL)
    UserRealm                :  ASGARD.CORP
    KeyType                  :  0x17 (unknown)
    Base64(key)              :  bsntG2x5Umfv9OIxCZrFHgkblbRK2P58kVqZSc5An/I=
    Base64EncodedTicket   :

      doIFwDCCBbygAwIBBaEDAgEWooIExjCCBMJhggS+MIIEuqADAgEFoQ0bC0FTR0FSRC5DT1JQ
"""


def test_rubeus_session_key_drops_unparseable_keytype(agent):
    """A key with an unknown etype is still worth having; a key labelled with
    the WRONG etype silently wastes an operator's time. When `KeyType` is not
    a clean identifier the prefix is omitted rather than guessed.
    """
    creds = RubeusParser().parse(RUBEUS_DUMP_ODD_KEYTYPE_SAMPLE, agent)
    keys = [c for c in creds if c.credtype == KRB_SESSION_KEY]

    assert len(keys) == 1
    assert keys[0].password == "bsntG2x5Umfv9OIxCZrFHgkblbRK2P58kVqZSc5An/I="


RUBEUS_DUMP_DES_KEY_SAMPLE = """
    ServiceName              :  krbtgt/ASGARD.CORP
    UserName                 :  LEO_MADDEN (NT_PRINCIPAL)
    UserRealm                :  ASGARD.CORP
    KeyType                  :  des_cbc_md5
    Base64(key)              :  QUFBQUFBQUE=
    Base64EncodedTicket   :

      doIFwDCCBbygAwIBBaEDAgEWooIExjCCBMJhggS+MIIEuqADAgEFoQ0bC0FTR0FSRC5DT1JQ
"""


def test_rubeus_keeps_legacy_des_session_key(agent):
    """A DES key is 8 bytes, which base64s to 12 characters — shorter than an
    rc4/aes key. A length floor set for the modern etypes drops it silently:
    the ticket lands, its key does not.
    """
    creds = RubeusParser().parse(RUBEUS_DUMP_DES_KEY_SAMPLE, agent)
    keys = [c for c in creds if c.credtype == KRB_SESSION_KEY]

    assert len(keys) == 1
    assert keys[0].password == "des_cbc_md5:QUFBQUFBQUE="


RUBEUS_KERBEROAST_SAMPLE = """
[*] Action: Kerberoasting

[*] SamAccountName         : sqlservice
[*] ServicePrincipalName   : MSSQLSvc/sql1.example.local:1433

$krb5tgs$23$*sqlservice$example.local$MSSQLSvc/sql1.example.local:1433*$DEADBEEF
    CAFEBABE0102030405060708
"""


def test_rubeus_kerberoast_extracts_tgs(agent):
    creds = RubeusParser().parse(RUBEUS_KERBEROAST_SAMPLE, agent)
    tgs = [c for c in creds if c.credtype == KRBTGS]
    assert len(tgs) == 1
    assert tgs[0].username == "sqlservice"
    assert tgs[0].password.endswith("DEADBEEFCAFEBABE0102030405060708")
    assert "kerberoast" in (tgs[0].notes or "")


RUBEUS_ASREPROAST_SAMPLE = """
[*] Action: AS-REP roasting

[*] SamAccountName         : noauthuser
[*] Hash written

$krb5asrep$23$noauthuser@EXAMPLE.LOCAL:AABB1122
    33445566778899AABBCCDDEEFF
"""


# ---------- Invoke-InternalMonologue -----------------------------------------


# Captured from a real Invoke-InternalMonologue run (hashcat mode 5500).
INTERNAL_MONOLOGUE_SAMPLE = b"""\
AROSE-WS01$::cyberdef:a663c2b423c438db1751609aa5d95e278e640796247657c4:a663c2b423c438db1751609aa5d95e278e640796247657c4:1122334455667788

m.torres::cyberdef:a8e83683ef2503f2e28859eb4bd7d1cc237cc11d77685a73:a8e83683ef2503f2e28859eb4bd7d1cc237cc11d77685a73:1122334455667788
"""


def test_internal_monologue_parses_netntlmv1(agent):
    creds = InternalMonologueParser().parse(INTERNAL_MONOLOGUE_SAMPLE, agent)

    assert len(creds) == 2  # noqa: PLR2004
    assert all(c.credtype == NETNTLMV1 for c in creds)

    by_user = {c.username: c for c in creds}
    assert "m.torres" in by_user
    m = by_user["m.torres"]
    assert m.domain == "cyberdef"
    assert m.password.startswith("m.torres::cyberdef:")
    assert m.password.endswith(":1122334455667788")
    assert m.notes == "internal_monologue"

    assert "AROSE-WS01$" in by_user
    ws = by_user["AROSE-WS01$"]
    assert "machine_account" in ws.notes


def test_internal_monologue_ignores_non_matching_lines(agent):
    data = b"[*] Banner line\n" + INTERNAL_MONOLOGUE_SAMPLE + b"[*] Done.\n"
    creds = InternalMonologueParser().parse(data, agent)
    assert len(creds) == 2  # noqa: PLR2004


def test_internal_monologue_tolerates_none_agent():
    """The CredentialParser Protocol allows `agent=None` for non-agent
    ingestion paths (plugins, file uploads). Parsers must not blow up
    on attribute access; host/os should fall back to empty/None.
    Locks the contract so a future "simplify the getattr defaults"
    refactor doesn't silently break plugin callers.
    """
    creds = InternalMonologueParser().parse(INTERNAL_MONOLOGUE_SAMPLE, None)
    assert len(creds) == 2  # noqa: PLR2004
    assert all(c.host == "" for c in creds)
    assert all(c.os is None for c in creds)


# ---------- Invoke-Inveigh ----------------------------------------------------


# Shaped like real Invoke-Inveigh console output: a header line per capture
# followed by the hashcat-format response. Mixes NTLMv2 (5600) and NTLMv1
# (5500), an SMB machine account, a local (domainless) account, a second
# distinct capture for an already-seen user, and a verbatim repeat of the
# first hash to exercise dedup.
INVEIGH_SAMPLE = b"""\
2026-08-21T12:00:01 - SMB NTLMv2 challenge/response captured from 10.0.0.5(WORKSTATION01):
m.torres::CYBERDEF:1122334455667788:a663c2b423c438db1751609aa5d95e27:0101000000000000c0653150de09d20100000000
2026-08-21T12:00:02 - HTTP NTLMv2 challenge/response captured from 10.0.0.6(WORKSTATION02):
AROSE-WS01$::CYBERDEF:1122334455667788:b774d3c534d549ec2862710bb6ea6f38:0101000000000000c0653150de09d20111111111
2026-08-21T12:00:03 - SMB NTLMv1 challenge/response captured from 10.0.0.7(WORKSTATION03):
j.doe::CYBERDEF:a8e83683ef2503f2e28859eb4bd7d1cc237cc11d77685a73:a8e83683ef2503f2e28859eb4bd7d1cc237cc11d77685a73:1122334455667788
2026-08-21T12:00:04 - SMB NTLMv2 challenge/response captured from 10.0.0.8(STANDALONE01):
localadmin:::1122334455667788:c885e4d645e65afd3973821cc7fb7049:0101000000000000c0653150de09d20122222222
2026-08-21T12:00:05 - SMB NTLMv2 challenge/response captured from 10.0.0.5(WORKSTATION01):
m.torres::CYBERDEF:99aabbccddeeff00:d996f5e756f76afe4984932dd8fc8f5a:0101000000000000c0653150de09d20133333333
2026-08-21T12:00:06 - SMB NTLMv2 challenge/response captured from 10.0.0.5(WORKSTATION01):
m.torres::CYBERDEF:1122334455667788:a663c2b423c438db1751609aa5d95e27:0101000000000000c0653150de09d20100000000
"""


def test_inveigh_parses_netntlmv1_and_v2(agent):
    creds = InveighParser().parse(INVEIGH_SAMPLE, agent)

    # 5 unique creds: the last line repeats the first verbatim and collapses.
    assert len(creds) == 5  # noqa: PLR2004

    # Deliberately not indexed by username — m.torres appears twice and a
    # username-keyed dict would hide the regression this asserts against.
    # Re-authentication yields a fresh challenge, so both captures are real
    # credentials; only a byte-identical repeat dedups. Keying `seen` on the
    # whole line is what buys that, and keying it on the username would not.
    torres_rows = [c for c in creds if c.username == "m.torres"]
    assert len(torres_rows) == 2  # noqa: PLR2004
    assert len({c.password for c in torres_rows}) == 2  # noqa: PLR2004
    assert all(c.credtype == NETNTLMV2 for c in torres_rows)
    assert all(c.domain == "CYBERDEF" for c in torres_rows)
    assert all(c.notes == "inveigh" for c in torres_rows)
    assert all(c.host == "WIN-AGENT" for c in torres_rows)

    doe = next(c for c in creds if c.username == "j.doe")
    assert doe.credtype == NETNTLMV1
    assert doe.password.endswith(":1122334455667788")

    machine = next(c for c in creds if c.username == "AROSE-WS01$")
    assert machine.credtype == NETNTLMV2
    assert "machine_account" in machine.notes

    # A local account capture carries no domain; the row must still be stored.
    local = next(c for c in creds if c.username == "localadmin")
    assert local.credtype == NETNTLMV2
    assert local.domain == ""


# Nothing in INVEIGH_SAMPLE exercises a near miss, so these pin the rejection
# side. One line per length-constrained segment of both patterns, so a relaxed
# quantifier anywhere is caught; plus a correct-length non-hex segment, since a
# widened character class (`[^:]`, `\w`) is the likelier accidental edit and no
# length case can catch it. The console-chatter lines are the noise Inveigh
# interleaves with captures — the spoofer status line embeds a comma-joined
# type list, making it the closest thing in real output to a false positive.
INVEIGH_NEAR_MISS = [
    # v2 challenge: 15 nibbles, wants 16
    b"short.challenge::CYBERDEF:112233445566778:a663c2b423c438db1751609aa5d95e27:0101000000000000",
    # v2 ntproof: 31 nibbles, wants 32
    b"short.ntproof::CYBERDEF:1122334455667788:a663c2b423c438db1751609aa5d95e2:0101000000000000",
    # v2 challenge: right length, not hex
    b"bad.hex::CYBERDEF:zzzzzzzzzzzzzzzz:a663c2b423c438db1751609aa5d95e27:0101000000000000",
    # v1 lmresp: 47 nibbles, wants 48
    b"short.lmresp::CYBERDEF:a8e83683ef2503f2e28859eb4bd7d1cc237cc11d77685a7:a8e83683ef2503f2e28859eb4bd7d1cc237cc11d77685a73:1122334455667788",
    # v1 ntresp: 47 nibbles, wants 48
    b"short.ntresp::CYBERDEF:a8e83683ef2503f2e28859eb4bd7d1cc237cc11d77685a73:a8e83683ef2503f2e28859eb4bd7d1cc237cc11d77685a7:1122334455667788",
    # v1 challenge: 15 nibbles, wants 16
    b"short.v1chal::CYBERDEF:a8e83683ef2503f2e28859eb4bd7d1cc237cc11d77685a73:a8e83683ef2503f2e28859eb4bd7d1cc237cc11d77685a73:112233445566778",
    # console chatter, not captures
    b"WARNING: Inveigh is running",
    b"2026-08-21T12:00:00 - NBNS Spoofer For Types 00,20 = Enabled",
    b"2026-08-21T12:05:00 - Inveigh exited",
]


@pytest.mark.parametrize("line", INVEIGH_NEAR_MISS)
def test_inveigh_rejects_near_miss_and_noise_lines(agent, line):
    assert InveighParser().parse(line, agent) == []


# ---------- tgtdelegation BOF -------------------------------------------------


TGTDELEG_SAMPLE = """\
[+] Found a DC for the domain cyberdef!
[+] DC: \\\\arose-DC01.cyberdef.lab
[+] No SPN specified! Using default SPN...
[+] Target SPN: CIFS/arose-DC01.cyberdef.lab
[+] Successfully obtained a handle to the current credentials set!
[+] Successfully initialized the Kerberos GSS-API!
[+] The delegation request was successful! AP-REQ ticket is now in the GSS-API output.
[+] Successfully invoked LsaCallAuthenticationPackage! The Kerberos session key should be cached!
[+] Job nonce: 6789

[+] AP-REQ output:
YIIMzQYJKoZIhvcSAQICAQBuggy8MIIMuKADAgEFoQMCAQ6iBwMFACAAAACjggUW
YYIFEjCCBQ6gAwIBBaEOGwxDWUJFUkRFRi5MQUKiKjAooAMCAQKhITAfGwRjaWZz

[+] Kerberos session key:
TvELnLa0wzzHRmt4TSHHZyvijBIr/tqvqlXwC5bLH0k=

[+] Encryption:
AES256
[+] tgtdelegation succeeded!
"""


def test_tgtdelegation_emits_ticket_with_json_envelope(agent):
    creds = TgtDelegationParser().parse(TGTDELEG_SAMPLE, agent)

    assert len(creds) == 1
    c = creds[0]
    assert c.credtype == KRB_TICKET
    assert c.username == "(current_user)"
    assert c.domain == "cyberdef.lab"
    assert c.notes == "tgtdelegation"

    payload = json.loads(c.password)
    assert payload["spn"] == "CIFS/arose-DC01.cyberdef.lab"
    assert payload["encryption"] == "AES256"
    assert payload["session_key"] == "TvELnLa0wzzHRmt4TSHHZyvijBIr/tqvqlXwC5bLH0k="
    # AP-REQ should be a single concatenated base64 line (wrap stripped).
    assert "\n" not in payload["apreq"]
    assert payload["apreq"].startswith("YIIMzQYJKoZIhvcSAQICAQBu")
    assert payload["dc"] == "arose-DC01.cyberdef.lab"


def test_tgtdelegation_requires_both_halves(agent):
    # AP-REQ alone without session key → nothing emitted.
    partial = "[+] AP-REQ output:\nYIIMzQYJKoZI\n\n[+] Encryption:\nAES256\n"
    assert TgtDelegationParser().parse(partial, agent) == []


# ---------- Invoke-NTLMExtract -----------------------------------------------


# Captured from a real `Invoke-NTLMExtract` run — PowerShell PSCustomObject
# output via the default Out-String formatter.
NTLMEXTRACT_SAMPLE = b"""\
@{Username=Administrator; NTLM=31D6CFE0D16AE931B73C59D7E0C089C0; RID=500}

@{Username=Guest; NTLM=31D6CFE0D16AE931B73C59D7E0C089C0; RID=501}

@{Username=DefaultAccount; NTLM=31D6CFE0D16AE931B73C59D7E0C089C0; RID=503}

@{Username=WDAGUtilityAccount; NTLM=A230164C4990A355EA2954067BDDB449; RID=504}

@{Username=localuser; NTLM=8846F7EAEE8FB117AD06BDD830B7586C; RID=1000}
"""


def test_ntlmextract_parses_pscustomobject_blocks(agent):
    creds = NtlmExtractParser().parse(NTLMEXTRACT_SAMPLE, agent)

    assert len(creds) == 5  # noqa: PLR2004
    assert all(c.credtype == HASH for c in creds)

    by_user = {c.username: c for c in creds}
    assert by_user["localuser"].password == "8846f7eaee8fb117ad06bdd830b7586c"
    assert by_user["Administrator"].password == "31d6cfe0d16ae931b73c59d7e0c089c0"
    assert all(c.notes == "ntlmextract" for c in creds)


def test_ntlmextract_preserves_machine_accounts(agent):
    data = b"@{Username=WS01$; NTLM=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; RID=1001}\n"
    creds = NtlmExtractParser().parse(data, agent)
    assert len(creds) == 1
    assert creds[0].username == "WS01$"
    assert "machine_account" in creds[0].notes


def test_ntlmextract_ignores_malformed_blocks(agent):
    data = b"@{NotAHash=foo; Bar=baz}\n@{Username=admin; NTLM=notreallyahex; RID=500}\n"
    assert NtlmExtractParser().parse(data, agent) == []


# ---------- SharpSecDump ------------------------------------------------------


# Captured from a real `Invoke-SharpSecDump -Target 127.0.0.1` run.
SHARPSECDUMP_SAMPLE = b"""\
[*] RemoteRegistry service started on localhost
[*] Parsing SAM hive on localhost
[*] Parsing SECURITY hive on localhost
[*] Sucessfully cleaned up on localhost

---------------Results from localhost---------------

[*] SAM hashes
Administrator:500:aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0
Guest:501:aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0
DefaultAccount:503:aad3b435b51404eeaad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0
WDAGUtilityAccount:504:aad3b435b51404eeaad3b435b51404ee:a230164c4990a355ea2954067bddb449
localuser:1000:aad3b435b51404eeaad3b435b51404ee:8846f7eaee8fb117ad06bdd830b7586c

[*] C4ched dOmain lOgon iNformation(Domain/Username:hash)
CYBERDEF.LAB/domainuser:$DCC2$10240#domainuser#bc288977024a638d19c10f34b9f01779
CYBERDEF.LAB/s.chen:$DCC2$10240#s.chen#a33ca0502a130cc136eedc62da0e8a5c
CYBERDEF.LAB/j.wilson:$DCC2$10240#j.wilson#87c698e695e28b1e0685a2fe2e263323
CYBERDEF.LAB/m.torres:$DCC2$10240#m.torres#7db00fc002a86b297bd3520993ed15f1

[*] LsA SEcrEts

[*] $MACHINE.ACC
cyberdef.lab\\arose-WS01$:aad3b435b51404eeaad3b435b51404ee:ddb17d4bf96509b0073a0c5e7b1e3b96

[*] DefaultPassword
[!] SEcret tYpe not sUpported Yet - Outputing Raw sEcret aS unicode:
password

[*] DPAPI_SYSTEM
dpapi_machinekey:b0ed3b55bb0c26041a110d2444589d7e8a05dcdc
dpapi_userkey:94b75cfbd43a4543db72537a2306397bbcac91ab

[X] No secrets to parse

---------------Script execution completed---------------
"""


def test_sharpsecdump_parses_sam_hashes(agent):
    creds = SharpSecDumpParser().parse(SHARPSECDUMP_SAMPLE, agent)
    sam = [c for c in creds if c.credtype == HASH and not c.domain]

    users = {c.username for c in sam}
    assert {
        "Administrator",
        "Guest",
        "DefaultAccount",
        "WDAGUtilityAccount",
        "localuser",
    } <= users
    # Empty LM is dropped, only NT hash stored.
    localuser = next(c for c in sam if c.username == "localuser")
    assert localuser.password == "8846f7eaee8fb117ad06bdd830b7586c"
    assert "sharpsecdump" in localuser.notes


def test_sharpsecdump_parses_dcc2(agent):
    creds = SharpSecDumpParser().parse(SHARPSECDUMP_SAMPLE, agent)
    dcc2 = [c for c in creds if c.credtype == DCC2]
    assert len(dcc2) == 4  # noqa: PLR2004

    by_user = {c.username: c for c in dcc2}
    torres = by_user["m.torres"]
    assert torres.domain == "CYBERDEF.LAB"
    assert torres.password == "$DCC2$10240#m.torres#7db00fc002a86b297bd3520993ed15f1"


def test_sharpsecdump_parses_machine_account(agent):
    creds = SharpSecDumpParser().parse(SHARPSECDUMP_SAMPLE, agent)
    machine = [
        c
        for c in creds
        if c.credtype == HASH
        and c.username.endswith("$")
        and "machine_account" in (c.notes or "")
    ]
    assert len(machine) == 1
    m = machine[0]
    assert m.username == "arose-WS01$"
    assert m.domain == "cyberdef.lab"
    assert m.password == "ddb17d4bf96509b0073a0c5e7b1e3b96"


def test_sharpsecdump_parses_default_password(agent):
    creds = SharpSecDumpParser().parse(SHARPSECDUMP_SAMPLE, agent)
    plain = [c for c in creds if c.credtype == PLAINTEXT]
    assert len(plain) == 1
    assert plain[0].username == "(autologon)"
    assert plain[0].password == "password"
    assert "default_password" in plain[0].notes


def test_sharpsecdump_parses_dpapi_system(agent):
    creds = SharpSecDumpParser().parse(SHARPSECDUMP_SAMPLE, agent)
    dpapi = [c for c in creds if c.credtype == DPAPI_SYSTEM_KEY]
    assert len(dpapi) == 2  # noqa: PLR2004

    by_name = {c.username: c for c in dpapi}
    assert by_name["dpapi_machinekey"].password == (
        "b0ed3b55bb0c26041a110d2444589d7e8a05dcdc"
    )
    assert by_name["dpapi_userkey"].password == (
        "94b75cfbd43a4543db72537a2306397bbcac91ab"
    )


def test_rubeus_asreproast_extracts_hash(agent):
    creds = RubeusParser().parse(RUBEUS_ASREPROAST_SAMPLE, agent)
    asrep = [c for c in creds if c.credtype == KRBASREP]
    assert len(asrep) == 1
    assert asrep[0].username == "noauthuser"
    assert asrep[0].domain == "EXAMPLE.LOCAL"
    assert asrep[0].password.endswith("AABB112233445566778899AABBCCDDEEFF")
    assert "asreproast" in (asrep[0].notes or "")


# ---------- Protocol contract: all parsers tolerate agent=None ----------------


# (parser_class, sample) pairs for the contract sweep. Each sample is the
# same fixture the parser's own happy-path test uses, so we know it
# produces ≥1 credential and exercises the agent-dereference path inside
# the result builder (not just the parse() entry point). When adding a
# new parser, add it here too — the Protocol contract applies to every
# parser, and internal_monologue alone is not a sufficient pin.
_PARSER_AGENT_NONE_SAMPLES = [
    (MimikatzParser, MIMIKATZ_SAMPLE),
    (PromptParser, b"[+] Prompted credentials: foo-> CORP\\jdoe : SecretPw!"),
    (KerberoastParser, KERBEROAST_RUBEUS_SAMPLE),
    (RubeusParser, RUBEUS_ASKTGT_SAMPLE),
    (PwdumpHashesParser, PWDUMP_SAMPLE),
    (SharpDpapiParser, SHARP_DPAPI_MASTERKEYS),
    (SessionGopherParser, SESSION_GOPHER_CSV),
    (InternalMonologueParser, INTERNAL_MONOLOGUE_SAMPLE),
    (SharpSecDumpParser, SHARPSECDUMP_SAMPLE),
    (NtlmExtractParser, NTLMEXTRACT_SAMPLE),
    (TgtDelegationParser, TGTDELEG_SAMPLE),
    (InveighParser, INVEIGH_SAMPLE),
]


@pytest.mark.parametrize(
    ("parser_cls", "sample"),
    _PARSER_AGENT_NONE_SAMPLES,
    ids=[cls.__name__ for cls, _ in _PARSER_AGENT_NONE_SAMPLES],
)
def test_parser_tolerates_none_agent(parser_cls, sample):
    """Protocol contract sweep: every registered parser must accept
    `agent=None` without raising. internal_monologue gets its own
    dedicated test (above) with stricter host/os assertions; this one
    pins the no-AttributeError contract for the rest, since they all
    use the same `getattr(agent, ...)` defensive pattern that a future
    "simplify the defaults away" refactor could silently break.
    """
    creds = parser_cls().parse(sample, None)
    # We only assert the call returned without raising. Counts and
    # field values are pinned in each parser's own happy-path test.
    assert isinstance(creds, list)

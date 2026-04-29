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

"""Credtype vocabulary used by credential parsers.

Each constant is the exact string written to `Credential.credtype`. Parsers
should reference these constants rather than free-typing the literals.

The `password` column holds different secret material per credtype:

    HASH               — 32-char NTLM hex, or "<lm>:<nt>" when a non-empty
                         LM half is present.
    PLAINTEXT          — recovered plaintext password
    NETNTLMV1          — NetNTLMv1 response (hashcat mode 5500)
                         Format: user::domain:lmresp:ntresp:challenge
    DCC2               — Domain Cached Credentials v2 (hashcat mode 2100)
                         Format: $DCC2$10240#user#hash
    KRBTGS             — full Hashcat/John $krb5tgs$... blob (single line)
    KRBASREP           — full Hashcat/John $krb5asrep$... blob (single line)
    KRB_TICKET         — base64 .kirbi (pass-the-ticket) or JSON envelope
                         packing AP-REQ + session key (tgtdelegation).
    DPAPI_MASTERKEY    — masterkey GUID joined to its SHA1-derived key.
                         Format: <guid>:<sha1_hex>
    DPAPI_SYSTEM_KEY   — DPAPI_SYSTEM LSA secret (machine or user hex key)
    DPAPI_VAULT_CRED   — json.dumps({"url":..., "username":..., "password":...})

`notes` carries the tool name plus a timestamp so operators can filter by
origin without a schema migration.
"""

HASH = "hash"
PLAINTEXT = "plaintext"
NETNTLMV1 = "netntlmv1"
DCC2 = "dcc2"
KRBTGS = "krbtgs"
KRBASREP = "krbasrep"
KRB_TICKET = "krb_ticket"
DPAPI_MASTERKEY = "dpapi_masterkey"
DPAPI_SYSTEM_KEY = "dpapi_system_key"
DPAPI_VAULT_CRED = "dpapi_vault_cred"

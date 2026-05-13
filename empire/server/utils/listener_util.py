import secrets
from textwrap import dedent

from empire.server.common import helpers

BYTE_MAX = 255


def remove_lines_comments(lines):
    """
    Remove lines comments.
    """
    code = ""
    for line in lines.split("\n"):
        _line = line.strip()
        # skip commented line
        if not _line.startswith("#"):
            code += _line
    return code


def looks_like_decimal_blob(b: bytes) -> bool:
    """
    Heuristic: returns True if b decodes as ASCII and contains only digits and
    common separators (space, comma, brackets, newlines, minus).
    """
    if not isinstance(b, bytes):
        return False
    try:
        s = bytes(b).decode("ascii")
    except UnicodeDecodeError:
        return False
    if not any(ch.isdigit() for ch in s):  # must contain at least one digit
        return False
    allowed = set("0123456789- \t\r\n,;[]()")
    return all(ch in allowed for ch in s)


def decimals_to_bytes(x):
    """Convert '237 30 211 ...' (bytes or str) into real bytes."""
    if isinstance(x, bytes):
        x = bytes(x).decode("ascii")
    # normalize separators
    for c in ",;[]()\t\r\n":
        x = x.replace(c, " ")
    vals = [int(tok) for tok in x.split() if tok]
    if not vals:
        raise ValueError("No integers found")
    if any(v < 0 or v > BYTE_MAX for v in vals):
        bad = [v for v in vals if v < 0 or v > BYTE_MAX][:5]
        raise ValueError(f"Out-of-range byte(s): {bad} (expected 0..255)")
    return bytes(vals)


def ensure_raw_bytes(x):
    """
    Helper function for malleable listener where encoding may not be consistent.
    If x looks like a decimal blob, convert it to raw bytes.
    """
    return decimals_to_bytes(x) if looks_like_decimal_blob(x) else bytes(x)


def python_extract_stager(staging_key):
    """
    Download the stager and extract the IV for Python agent.
    """
    stager = dedent(
        """
    exec(data);
    """
    )
    return helpers.strip_python_comments(stager)


def generate_random_cipher():
    """
    Return FIPS-approved TLS 1.2 cipher suites (AEAD + forward secrecy)
    in randomized order for JA3 evasion. Both suites are included so
    OpenSSL can negotiate even if one is unavailable on the platform.
    """
    ciphers = [
        "ECDHE-RSA-AES256-GCM-SHA384",
        "ECDHE-RSA-AES128-GCM-SHA256",
    ]
    shuffled = secrets.SystemRandom().sample(ciphers, len(ciphers))
    return ":".join(shuffled)

"""Self-signed certificate generation for the Empire server.

Replaces the former ``setup/cert.sh``. A wheel install has no ``setup/``
directory, and a Python package's runtime closure cannot assume ``/bin/bash``
or an ``openssl`` binary exist -- so this reproduces what
``openssl req -new -x509 -newkey rsa:4096 -days 365 -nodes -subj /C=US`` did,
in process, using the ``cryptography`` dependency Empire already declares.
"""

import datetime
import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CERT_FILENAME = "empire-chain.pem"
KEY_FILENAME = "empire-priv.key"

_KEY_SIZE = 4096
_VALID_DAYS = 365


def generate_self_signed_cert(cert_dir: Path) -> tuple[Path, Path]:
    """Write a self-signed RSA-4096 certificate and key into ``cert_dir``.

    Raises on failure: the shell script this replaces ran through
    ``subprocess.call``, whose ignored exit code let the server boot with no
    certificate at all.

    Any failure partway through must leave one of the two files *absent* --
    the only state ``server.run``'s "regenerate when either half is missing"
    gate can detect. The unlink and the staged write below hold that
    invariant.
    """
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / CERT_FILENAME
    key_path = cert_dir / KEY_FILENAME

    key = rsa.generate_private_key(public_exponent=65537, key_size=_KEY_SIZE)
    public_key = key.public_key()
    name = x509.Name([x509.NameAttribute(NameOID.COUNTRY_NAME, "US")])
    not_valid_before = datetime.datetime.now(datetime.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_valid_before)
        .not_valid_after(not_valid_before + datetime.timedelta(days=_VALID_DAYS))
        # openssl.cnf's default `[req] x509_extensions = v3_ca` put these three
        # on every cert `openssl req -x509` produced, so operators who imported
        # the old PEM into a trust store (powershell/management/
        # install_root_certificate) got a CA. Omitting them silently downgrades
        # that cert to a bare leaf. AKI equals SKI on a self-signed root, but
        # openssl emits it and some trust stores expect it, so match exactly.
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(public_key),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    # Before the key write, so a crash between the two cannot leave a pair
    # that looks matched.
    cert_path.unlink(missing_ok=True)

    # 0600, matching openssl's bio_open_owner(): under ps-empire's `sudo -E` a
    # umask-default 0644 key is root-owned and world-readable. O_CREAT's mode
    # is ignored for an existing file, so the fchmod must precede the write --
    # otherwise a rotation holds the fresh secret at the stale, looser mode.
    # O_NOFOLLOW refuses the open when key_path is a symlink: under `sudo -E`
    # the server is root but DATA_DIR sits in the invoking user's HOME, so a
    # local user could otherwise plant a symlink here and have root follow it,
    # truncating an arbitrary root-owned file and chmod'ing it to 0600.
    key_fd = os.open(
        key_path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, 0o600
    )
    os.fchmod(key_fd, 0o600)
    with os.fdopen(key_fd, "wb") as f:
        f.write(
            # PKCS#8 ("BEGIN PRIVATE KEY"), which is what `openssl req -keyout
            # ... -nodes` has emitted since 1.0; TraditionalOpenSSL would hand
            # a PKCS#1 body to consumers that only accept the former.
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    # Staged, so the certificate appears at its real path only once complete:
    # a torn write leaves a truncated cert *present*, which the gate reads as
    # healthy. O_NOFOLLOW for the same reason as the key above: under `sudo -E`
    # a local user could pre-plant this staged path as a symlink and have root
    # follow it, truncating an arbitrary root-owned file. The cert is public,
    # but the truncation is the damage; the final os.replace is symlink-safe on
    # its own.
    staged_cert = cert_path.with_name(cert_path.name + ".tmp")
    cert_fd = os.open(
        staged_cert, os.O_CREAT | os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW, 0o644
    )
    with os.fdopen(cert_fd, "wb") as f:
        f.write(certificate.public_bytes(serialization.Encoding.PEM))
    staged_cert.replace(cert_path)
    return cert_path, key_path

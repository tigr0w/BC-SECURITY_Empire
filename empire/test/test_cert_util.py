"""Unit tests for the in-process replacement for setup/cert.sh."""

import datetime
import errno
import os
import stat

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from empire.server.utils import cert_util

RSA_KEY_SIZE = 4096


@pytest.fixture(scope="module")
def generated_pair(tmp_path_factory):
    """One RSA-4096 keygen shared by every test that only reads a good pair.

    Regenerating per test costs seconds apiece for no extra coverage; the
    tests that need a *specific* pre-existing on-disk state build their own.
    """
    return cert_util.generate_self_signed_cert(tmp_path_factory.mktemp("cert"))


def test_generates_the_pair_with_the_openssl_parameters(generated_pair):
    """Reproduce `openssl req -newkey rsa:4096 -days 365 -subj /C=US` exactly."""
    cert_path, key_path = generated_pair

    assert cert_path.name == "empire-chain.pem"
    assert key_path.name == "empire-priv.key"

    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    assert isinstance(cert.public_key(), rsa.RSAPublicKey)
    assert cert.public_key().key_size == RSA_KEY_SIZE
    assert cert.subject == cert.issuer
    assert cert.subject.rfc4514_string() == "C=US"

    lifetime = cert.not_valid_after_utc - cert.not_valid_before_utc
    assert lifetime == datetime.timedelta(days=365)


def test_carries_the_v3_ca_extensions_openssl_added_by_default(generated_pair):
    """`openssl req -x509` applies openssl.cnf's `v3_ca` block.

    Dropping it turns the cert operators have always imported into a trust
    store (powershell/management/install_root_certificate) into a bare leaf,
    and nothing else in the suite would notice.
    """
    cert_path, _ = generated_pair
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())

    basic = cert.extensions.get_extension_for_class(x509.BasicConstraints)
    assert basic.critical
    assert basic.value.ca is True

    # SKI and AKI both present, and equal, as openssl emits for a self-signed
    # root: the AKI's key identifier points back at this cert's own SKI.
    ski = cert.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
    aki = cert.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier)
    assert aki.value.key_identifier == ski.value.digest


def test_private_key_is_not_world_readable(generated_pair):
    """`openssl req -keyout` writes 0600; a naive write_bytes leaves 0644.

    ps-empire runs the server under `sudo -E`, so the naive version yields a
    root-owned world-readable 4096-bit TLS private key -- the same key
    operators point listeners' CertPath at.
    """
    _, key_path = generated_pair

    mode = stat.S_IMODE(key_path.stat().st_mode)
    assert mode == 0o600, f"private key mode is {mode:#o}, expected 0o600"  # noqa: PLR2004


def test_private_key_is_unencrypted_and_loadable(generated_pair):
    """The old script passed -nodes; uvicorn loads the key without a password."""
    _, key_path = generated_pair

    pem = key_path.read_bytes()
    # PKCS#8, matching `openssl req -keyout ... -nodes`; the PKCS#1 header
    # ("BEGIN RSA PRIVATE KEY") is what TraditionalOpenSSL would emit.
    assert pem.startswith(b"-----BEGIN PRIVATE KEY-----")

    key = serialization.load_pem_private_key(pem, password=None)
    assert key.key_size == RSA_KEY_SIZE


def test_rewriting_an_existing_key_still_lands_at_0600(tmp_path):
    """O_CREAT's mode argument is ignored when the file already exists."""
    cert_dir = tmp_path / "cert"
    cert_dir.mkdir()
    stale = cert_dir / "empire-priv.key"
    stale.write_text("stale")
    stale.chmod(0o644)

    _, key_path = cert_util.generate_self_signed_cert(cert_dir)

    assert stat.S_IMODE(key_path.stat().st_mode) == 0o600  # noqa: PLR2004


def test_a_planted_symlink_key_is_refused_not_followed(tmp_path):
    """Under `sudo -E` the server is root but the cert dir is user-writable.

    A local user who pre-plants the key path as a symlink must not get root to
    follow it: without O_NOFOLLOW the open would truncate the symlink's target
    (an arbitrary root-owned file) and then fchmod it to 0600.
    """
    cert_dir = tmp_path / "cert"
    cert_dir.mkdir()
    victim = tmp_path / "victim"
    victim.write_bytes(b"do not truncate me")
    (cert_dir / "empire-priv.key").symlink_to(victim)

    with pytest.raises(OSError, match="symbolic link") as exc_info:
        cert_util.generate_self_signed_cert(cert_dir)
    assert exc_info.value.errno == errno.ELOOP

    assert victim.read_bytes() == b"do not truncate me"


def test_a_planted_symlink_cert_is_refused_not_followed(tmp_path):
    """The staged certificate write needs the same O_NOFOLLOW as the key.

    The cert is public, but a symlink pre-planted at the staged `.tmp` path
    would still let root truncate an arbitrary root-owned file under `sudo -E`.
    """
    cert_dir = tmp_path / "cert"
    cert_dir.mkdir()
    victim = tmp_path / "victim"
    victim.write_bytes(b"do not truncate me")
    (cert_dir / "empire-chain.pem.tmp").symlink_to(victim)

    with pytest.raises(OSError, match="symbolic link") as exc_info:
        cert_util.generate_self_signed_cert(cert_dir)
    assert exc_info.value.errno == errno.ELOOP

    assert victim.read_bytes() == b"do not truncate me"


def test_a_failed_run_never_leaves_a_stale_cert_beside_a_fresh_key(tmp_path):
    """server.run only regenerates when a *half* is missing.

    So an interrupted run must leave one of the two files absent. Leaving the
    previous certificate next to a newly written key would satisfy that gate
    forever while uvicorn and every listener fail on "key values mismatch".
    """
    cert_dir = tmp_path / "cert"
    cert_dir.mkdir()
    stale_cert = cert_dir / "empire-chain.pem"
    stale_cert.write_text("stale certificate for a key that no longer exists")
    # A directory where the key file belongs makes the key write blow up
    # partway through, standing in for ENOSPC / EACCES / the process being
    # killed between the two writes.
    (cert_dir / "empire-priv.key").mkdir()

    with pytest.raises(IsADirectoryError):
        cert_util.generate_self_signed_cert(cert_dir)

    assert not stale_cert.exists(), (
        "the stale certificate survived a failed regeneration; server.run "
        "will now skip regeneration forever with a mismatched pair"
    )


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_failure_raises_rather_than_leaving_the_boot_certificateless(tmp_path):
    """The old subprocess.call ignored the return code -- that was the defect."""
    unwritable = tmp_path / "readonly"
    unwritable.mkdir(mode=0o500)

    with pytest.raises(PermissionError):
        cert_util.generate_self_signed_cert(unwritable / "cert")

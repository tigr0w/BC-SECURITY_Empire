"""Tests for PBKDF2 password hashing (FIPS SP 800-132).

Tests use the `client` fixture even though they don't send HTTP requests —
it triggers the session-scoped DB setup required by jwt_auth's module-level
SECRET_KEY query.
"""


class TestPBKDF2Hashing:
    def test_hash_format(self, client):
        """PBKDF2 hash should follow pbkdf2:algo:iterations$salt$hash format."""
        from empire.server.api.jwt_auth import get_password_hash

        hashed = get_password_hash("test_password")
        header, salt_hex, hash_hex = hashed.split("$")
        algo_parts = header.split(":")

        assert algo_parts[0] == "pbkdf2"
        assert algo_parts[1] == "sha256"
        assert algo_parts[2] == "600000"
        assert len(bytes.fromhex(salt_hex)) == 16  # noqa: PLR2004
        assert len(bytes.fromhex(hash_hex)) == 32  # noqa: PLR2004

    def test_verify_roundtrip(self, client):
        """A password should verify against its own hash."""
        from empire.server.api.jwt_auth import get_password_hash, verify_password

        password = "my_secure_password"
        hashed = get_password_hash(password)
        assert verify_password(password, hashed) is True

    def test_wrong_password_rejected(self, client):
        """An incorrect password should not verify."""
        from empire.server.api.jwt_auth import get_password_hash, verify_password

        hashed = get_password_hash("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_unique_salts(self, client):
        """Each hash should use a unique salt."""
        from empire.server.api.jwt_auth import get_password_hash, verify_password

        h1 = get_password_hash("same_password")
        h2 = get_password_hash("same_password")
        assert h1 != h2
        assert verify_password("same_password", h1) is True
        assert verify_password("same_password", h2) is True

    def test_malformed_hash_rejected(self, client):
        """Malformed hash strings should not verify."""
        from empire.server.api.jwt_auth import verify_password

        assert verify_password("test", "not_a_valid_hash") is False
        assert verify_password("test", "") is False
        assert verify_password("test", "pbkdf2:sha256:600000$bad") is False
        assert verify_password("test", "pbkdf2:sha256:600000$ZZZZ$aabb") is False
        assert verify_password("test", "pbkdf2:sha256:notanumber$aabb$ccdd") is False

    def test_bcrypt_hash_rejected(self, client):
        """Legacy bcrypt hashes must be rejected (no backward compatibility)."""
        from empire.server.api.jwt_auth import verify_password

        bcrypt_hash = "$2b$12$LJ3m4ys3LfDLqMEnOaaFreFEHrWdEFmSHOuDKLmmkbLhLmKCuby4q"
        assert verify_password("password", bcrypt_hash) is False

    def test_empty_password_roundtrip(self, client):
        """Empty string password should hash and verify."""
        from empire.server.api.jwt_auth import get_password_hash, verify_password

        hashed = get_password_hash("")
        assert verify_password("", hashed) is True
        assert verify_password("notempty", hashed) is False

    def test_unicode_password_roundtrip(self, client):
        """Unicode passwords should hash and verify correctly."""
        from empire.server.api.jwt_auth import get_password_hash, verify_password

        password = "p\u00e4ssw\u00f6rd\U0001f512"
        hashed = get_password_hash(password)
        assert verify_password(password, hashed) is True
        assert verify_password("password", hashed) is False

    def test_long_password_roundtrip(self, client):
        """Long passwords (>72 bytes) should work — no bcrypt truncation."""
        from empire.server.api.jwt_auth import get_password_hash, verify_password

        password = "A" * 1000
        hashed = get_password_hash(password)
        assert verify_password(password, hashed) is True
        assert verify_password("A" * 999, hashed) is False


class TestDefaultsInterop:
    def test_default_password_verifies(self, client):
        """Hash from defaults.py must verify with jwt_auth.verify_password."""
        from empire.server.api.jwt_auth import verify_password
        from empire.server.core.db.defaults import get_default_hashed_password

        hashed = get_default_hashed_password()
        assert verify_password("password123", hashed) is True
        assert verify_password("wrong", hashed) is False

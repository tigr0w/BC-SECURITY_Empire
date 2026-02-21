import base64
import tempfile
from binascii import hexlify
from pathlib import Path
from struct import pack

import pytest

from empire.server.utils.bof_packer import bof_pack, process_arguments


def test_bof_pack_binary_file():
    """Test that bof_pack reads a binary file and packs it correctly."""
    content = b"\xde\xad\xbe\xef"
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
        f.write(content)
        temp_path = f.name

    try:
        result = bof_pack("b", [temp_path])
        # The result should be: 4-byte LE size header + 4-byte LE length + content + null
        # content with null = 5 bytes, length field = 4 bytes -> inner = 9 bytes
        inner_len = 4 + len(content) + 1  # length prefix + data + null terminator
        expected_size = pack("<L", inner_len)
        expected_inner = pack(f"<L{len(content) + 1}s", len(content) + 1, content)
        assert result == expected_size + expected_inner
    finally:
        Path(temp_path).unlink()


def test_bof_pack_int():
    """Test packing an integer argument."""
    result = bof_pack("i", ["42"])
    inner = pack("<i", 42)
    expected = pack("<L", len(inner)) + inner
    assert result == expected


def test_bof_pack_short():
    """Test packing a short argument."""
    result = bof_pack("s", ["7"])
    inner = pack("<h", 7)
    expected = pack("<L", len(inner)) + inner
    assert result == expected


def test_bof_pack_string():
    """Test packing a UTF-8 string argument."""
    result = bof_pack("z", ["hello"])
    encoded = b"hello"
    inner = pack(f"<L{len(encoded) + 1}s", len(encoded) + 1, encoded)
    expected = pack("<L", len(inner)) + inner
    assert result == expected


def test_bof_pack_wide_string():
    """Test packing a wide (UTF-16LE) string argument."""
    result = bof_pack("Z", ["hi"])
    encoded = "hi".encode("utf-16_le")
    inner = pack(f"<L{len(encoded) + 2}s", len(encoded) + 2, encoded)
    expected = pack("<L", len(inner)) + inner
    assert result == expected


def test_bof_pack_mismatched_length():
    """Test that mismatched format string and args raises ValueError."""
    with pytest.raises(ValueError, match="Format string length must match"):
        bof_pack("ii", ["1"])


def test_bof_pack_invalid_format_char():
    """Test that an invalid format character raises ValueError."""
    with pytest.raises(ValueError, match="Invalid format character"):
        bof_pack("x", ["1"])


def test_process_arguments_with_binary():
    """Test process_arguments with binary file format."""
    content = b"\x01\x02\x03"
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
        f.write(content)
        temp_path = f.name

    try:
        result = process_arguments("b", temp_path)
        # result should be base64(hexlify(packed_data))
        packed = bof_pack("b", [temp_path])
        expected = base64.b64encode(hexlify(packed)).decode("utf-8")
        assert result == expected
    finally:
        Path(temp_path).unlink()


def test_process_arguments_with_quoted_string():
    """Test process_arguments correctly handles quoted strings."""
    result = process_arguments("z", '"hello world"')
    packed = bof_pack("z", ["hello world"])
    expected = base64.b64encode(hexlify(packed)).decode("utf-8")
    assert result == expected

"""Tests for kerf_core.storage.lfs_pointer — Git-LFS v1 pointer parse/serialize."""

import pytest

from kerf_core.storage.lfs_pointer import LfsPointerError, parse, serialize

# ---------------------------------------------------------------------------
# Known-good canonical fixture values
# ---------------------------------------------------------------------------

# A real Git-LFS pointer produced by `git lfs pointer --file` — the byte
# layout here is the authoritative canonical fixture for byte-exact round-trip.
CANONICAL_OID = "4d7a214614ab2935c943f9e0ff69d22eadbb8f32eb2bf690167fe7ee3520c9b2"
CANONICAL_SIZE = 12345
CANONICAL_BYTES = (
    b"version https://git-lfs.github.com/spec/v1\n"
    b"oid sha256:4d7a214614ab2935c943f9e0ff69d22eadbb8f32eb2bf690167fe7ee3520c9b2\n"
    b"size 12345\n"
)

# Second fixture: size == 0 (edge case)
ZERO_OID = "a" * 64
ZERO_BYTES = (
    b"version https://git-lfs.github.com/spec/v1\n"
    b"oid sha256:" + (b"a" * 64) + b"\n"
    b"size 0\n"
)


# ---------------------------------------------------------------------------
# serialize() — happy path
# ---------------------------------------------------------------------------


def test_serialize_canonical_fixture():
    """serialize() must produce the exact canonical bytes for the fixture OID/size."""
    result = serialize(CANONICAL_OID, CANONICAL_SIZE)
    assert result == CANONICAL_BYTES


def test_serialize_zero_size():
    result = serialize(ZERO_OID, 0)
    assert result == ZERO_BYTES


def test_serialize_large_size():
    oid = "b" * 64
    size = 2**40  # 1 TiB
    result = serialize(oid, size)
    assert result == (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:" + b"b" * 64 + b"\n"
        b"size " + str(size).encode() + b"\n"
    )


def test_serialize_returns_bytes():
    assert isinstance(serialize(CANONICAL_OID, CANONICAL_SIZE), bytes)


def test_serialize_lf_endings():
    result = serialize(CANONICAL_OID, CANONICAL_SIZE)
    assert b"\r" not in result
    assert result.endswith(b"\n")
    assert result.count(b"\n") == 3


# ---------------------------------------------------------------------------
# serialize() — validation errors
# ---------------------------------------------------------------------------


def test_serialize_bad_oid_short():
    with pytest.raises(LfsPointerError):
        serialize("abc123", 10)


def test_serialize_bad_oid_uppercase():
    with pytest.raises(LfsPointerError):
        serialize("A" * 64, 10)


def test_serialize_bad_oid_not_hex():
    with pytest.raises(LfsPointerError):
        serialize("g" * 64, 10)


def test_serialize_bad_oid_65_chars():
    with pytest.raises(LfsPointerError):
        serialize("a" * 65, 10)


def test_serialize_bad_oid_type():
    with pytest.raises(LfsPointerError):
        serialize(12345, 10)  # type: ignore[arg-type]


def test_serialize_negative_size():
    with pytest.raises(LfsPointerError):
        serialize(CANONICAL_OID, -1)


def test_serialize_size_bool():
    # bool is a subclass of int — must be rejected
    with pytest.raises(LfsPointerError):
        serialize(CANONICAL_OID, True)  # type: ignore[arg-type]


def test_serialize_size_float():
    with pytest.raises(LfsPointerError):
        serialize(CANONICAL_OID, 1.0)  # type: ignore[arg-type]


def test_serialize_size_string():
    with pytest.raises(LfsPointerError):
        serialize(CANONICAL_OID, "100")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# parse() — happy path (bytes input)
# ---------------------------------------------------------------------------


def test_parse_canonical_fixture():
    result = parse(CANONICAL_BYTES)
    assert result == {"oid": CANONICAL_OID, "size": CANONICAL_SIZE}


def test_parse_zero_size():
    result = parse(ZERO_BYTES)
    assert result == {"oid": ZERO_OID, "size": 0}


def test_parse_str_input():
    """parse() must accept str as well as bytes."""
    result = parse(CANONICAL_BYTES.decode("utf-8"))
    assert result == {"oid": CANONICAL_OID, "size": CANONICAL_SIZE}


def test_parse_returns_oid_without_prefix():
    result = parse(CANONICAL_BYTES)
    assert not result["oid"].startswith("sha256:")


def test_parse_returns_int_size():
    result = parse(CANONICAL_BYTES)
    assert isinstance(result["size"], int)


# ---------------------------------------------------------------------------
# Round-trip: serialize -> parse -> serialize
# ---------------------------------------------------------------------------


def test_round_trip_canonical():
    serialized = serialize(CANONICAL_OID, CANONICAL_SIZE)
    parsed = parse(serialized)
    assert parsed == {"oid": CANONICAL_OID, "size": CANONICAL_SIZE}
    # Second serialize must yield identical bytes
    assert serialize(parsed["oid"], parsed["size"]) == serialized  # type: ignore[arg-type]


def test_round_trip_zero():
    serialized = serialize(ZERO_OID, 0)
    parsed = parse(serialized)
    assert parsed == {"oid": ZERO_OID, "size": 0}
    assert serialize(parsed["oid"], parsed["size"]) == serialized  # type: ignore[arg-type]


def test_round_trip_all_hex_digits():
    oid = "0123456789abcdef" * 4  # 64 chars, all lowercase hex digits
    size = 999999999999
    assert parse(serialize(oid, size)) == {"oid": oid, "size": size}


# ---------------------------------------------------------------------------
# parse() — invalid inputs
# ---------------------------------------------------------------------------


def test_parse_empty():
    with pytest.raises(LfsPointerError):
        parse(b"")


def test_parse_missing_version_line():
    data = b"oid sha256:" + b"a" * 64 + b"\nsize 0\n"
    with pytest.raises(LfsPointerError):
        parse(data)


def test_parse_wrong_version():
    data = (
        b"version https://git-lfs.github.com/spec/v2\n"
        b"oid sha256:" + b"a" * 64 + b"\n"
        b"size 0\n"
    )
    with pytest.raises(LfsPointerError):
        parse(data)


def test_parse_missing_oid_line():
    data = b"version https://git-lfs.github.com/spec/v1\nsize 0\n"
    with pytest.raises(LfsPointerError):
        parse(data)


def test_parse_missing_size_line():
    data = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:" + b"a" * 64 + b"\n"
    )
    with pytest.raises(LfsPointerError):
        parse(data)


def test_parse_extra_line():
    data = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:" + b"a" * 64 + b"\n"
        b"size 0\n"
        b"extra key\n"
    )
    with pytest.raises(LfsPointerError):
        parse(data)


def test_parse_misordered_keys():
    # size before oid
    data = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"size 0\n"
        b"oid sha256:" + b"a" * 64 + b"\n"
    )
    with pytest.raises(LfsPointerError):
        parse(data)


def test_parse_oid_uppercase():
    data = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:" + b"A" * 64 + b"\n"
        b"size 0\n"
    )
    with pytest.raises(LfsPointerError):
        parse(data)


def test_parse_oid_wrong_length():
    data = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:" + b"a" * 63 + b"\n"
        b"size 0\n"
    )
    with pytest.raises(LfsPointerError):
        parse(data)


def test_parse_non_sha256_hash():
    # md5 prefix
    data = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid md5:abc123\n"
        b"size 0\n"
    )
    with pytest.raises(LfsPointerError):
        parse(data)


def test_parse_negative_size():
    data = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:" + b"a" * 64 + b"\n"
        b"size -1\n"
    )
    with pytest.raises(LfsPointerError):
        parse(data)


def test_parse_size_float():
    data = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:" + b"a" * 64 + b"\n"
        b"size 1.5\n"
    )
    with pytest.raises(LfsPointerError):
        parse(data)


def test_parse_size_leading_zeros():
    data = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:" + b"a" * 64 + b"\n"
        b"size 007\n"
    )
    with pytest.raises(LfsPointerError):
        parse(data)


def test_parse_crlf_line_endings():
    data = (
        b"version https://git-lfs.github.com/spec/v1\r\n"
        b"oid sha256:" + b"a" * 64 + b"\r\n"
        b"size 0\r\n"
    )
    with pytest.raises(LfsPointerError):
        parse(data)


def test_parse_no_trailing_lf():
    data = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:" + b"a" * 64 + b"\n"
        b"size 0"
    )
    with pytest.raises(LfsPointerError):
        parse(data)


def test_parse_invalid_input_type():
    with pytest.raises(LfsPointerError):
        parse(12345)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# LfsPointerError is a ValueError subclass
# ---------------------------------------------------------------------------


def test_lfs_pointer_error_is_value_error():
    with pytest.raises(ValueError):
        serialize("bad", 0)

"""GDS-II record type and data type constants (Calma GDSII Stream Format)."""

from __future__ import annotations

import struct
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Record type codes (1 byte, the second byte of every record header)
# ---------------------------------------------------------------------------

class RecordType:
    HEADER   = 0x00
    BGNLIB   = 0x01
    LIBNAME  = 0x02
    UNITS    = 0x03
    ENDLIB   = 0x04
    BGNSTR   = 0x05
    STRNAME  = 0x06
    ENDSTR   = 0x07
    BOUNDARY = 0x08
    PATH     = 0x09
    SREF     = 0x0A
    AREF     = 0x0B
    TEXT     = 0x0C
    LAYER    = 0x0D
    DATATYPE = 0x0E
    WIDTH    = 0x0F
    XY       = 0x10
    ENDEL    = 0x11
    SNAME    = 0x12
    COLROW   = 0x13
    TEXTNODE = 0x14
    NODE     = 0x15
    TEXTTYPE = 0x16
    PRESENTATION = 0x17
    SPACING  = 0x18
    STRING   = 0x19
    STRANS   = 0x1A
    MAG      = 0x1B
    ANGLE    = 0x1C
    UINTEGER = 0x1D
    USTRING  = 0x1E
    REFLIBS  = 0x1F
    FONTS    = 0x20
    PATHTYPE = 0x21
    GENERATIONS = 0x22
    ATTRTABLE = 0x23
    STYPTABLE = 0x24
    STRTYPE  = 0x25
    ELFLAGS  = 0x26
    ELKEY    = 0x27
    NODETYPE = 0x2A
    PROPATTR = 0x2B
    PROPVALUE = 0x2C


# ---------------------------------------------------------------------------
# Data type codes (1 byte, the third byte of every record header)
# ---------------------------------------------------------------------------

class DataType:
    NO_DATA   = 0x00
    BITARRAY  = 0x01
    INT16     = 0x02
    INT32     = 0x04
    REAL32    = 0x05   # GDS-II proprietary 32-bit real (not IEEE-754)
    REAL64    = 0x06   # GDS-II proprietary 64-bit real
    ASCII     = 0x06   # Alias — ASCII strings also encoded as 0x06 in record header


# ---------------------------------------------------------------------------
# GDS-II proprietary real encoding (NOT IEEE-754)
#
# Format (64-bit / 8-byte variant used for UNITS and REAL64):
#   Bit 63:    sign
#   Bits 62-56: exponent (excess-64, i.e. biased by 64), base-16 exponent
#   Bits 55-0:  56-bit unsigned mantissa, MSB first, value = mantissa / 2^56
#
# The actual value is:
#   (-1)^sign * mantissa / 2^56 * 16^(exponent - 64)
# ---------------------------------------------------------------------------

def float_to_gds_real(value: float) -> bytes:
    """Encode a Python float as an 8-byte GDS-II proprietary real."""
    if value == 0.0:
        return b'\x00' * 8

    sign = 0
    if value < 0:
        sign = 1
        value = -value

    # Normalise: find exponent (base-16) and mantissa
    # mantissa stored as fraction with implicit leading bit
    # We want: value = mantissa * 16^(exp - 64)  where 0.0625 <= mantissa < 1.0
    import math
    exp = 0
    # Scale value to [1/16, 1)
    # 16^exp_raw  such that 1/16 <= value / 16^exp_raw < 1
    if value != 0:
        log16 = math.log(value) / math.log(16)
        exp_raw = math.floor(log16) + 1   # biased so mantissa is in [1/16, 1)
        exp = exp_raw + 64                # add excess-64 bias
        mantissa_float = value / (16.0 ** exp_raw)

        # Clamp mantissa into [1/16, 1)
        while mantissa_float >= 1.0:
            mantissa_float /= 16.0
            exp += 1
        while mantissa_float != 0 and mantissa_float < 0.0625:
            mantissa_float *= 16.0
            exp -= 1

        # Clamp exponent to valid range [0, 127]
        if exp < 0:
            exp = 0
            mantissa_float = 0.0
        elif exp > 127:
            exp = 127
            mantissa_float = 1.0 - 1e-15   # saturate

    else:
        exp = 0
        mantissa_float = 0.0

    # Convert mantissa to 56-bit integer
    mantissa_int = int(round(mantissa_float * (2 ** 56)))
    # Clamp to 56-bit range
    mantissa_int = min(mantissa_int, (1 << 56) - 1)

    # Pack: byte0 = sign(1) | exponent(7)
    byte0 = (sign << 7) | (exp & 0x7F)
    # Remaining 7 bytes = mantissa big-endian
    result = bytearray(8)
    result[0] = byte0
    for i in range(7):
        result[7 - i] = mantissa_int & 0xFF
        mantissa_int >>= 8

    return bytes(result)


def gds_real_to_float(data: bytes) -> float:
    """Decode an 8-byte GDS-II proprietary real to a Python float."""
    if len(data) != 8:
        raise ValueError(f"Expected 8 bytes for GDS real, got {len(data)}")

    byte0 = data[0]
    sign = (byte0 >> 7) & 1
    exp = byte0 & 0x7F

    mantissa_int = 0
    for i in range(1, 8):
        mantissa_int = (mantissa_int << 8) | data[i]

    mantissa_float = mantissa_int / (2 ** 56)
    value = mantissa_float * (16.0 ** (exp - 64))

    if sign:
        value = -value
    return value


# ---------------------------------------------------------------------------
# Low-level record pack/unpack helpers
# ---------------------------------------------------------------------------

def pack_record(record_type: int, data_type: int, data: bytes) -> bytes:
    """Pack a single GDS-II record with a 4-byte header."""
    total_len = 4 + len(data)
    if total_len > 0xFFFF:
        raise ValueError(f"GDS record too long: {total_len} bytes")
    header = struct.pack(">HBB", total_len, record_type, data_type)
    return header + data


def pack_no_data(record_type: int) -> bytes:
    """Pack a record that carries no data (4-byte header only)."""
    return pack_record(record_type, DataType.NO_DATA, b"")


def pack_int16(record_type: int, values: List[int]) -> bytes:
    data = struct.pack(f">{len(values)}h", *values)
    return pack_record(record_type, DataType.INT16, data)


def pack_int32(record_type: int, values: List[int]) -> bytes:
    data = struct.pack(f">{len(values)}i", *values)
    return pack_record(record_type, DataType.INT32, data)


def pack_real64(record_type: int, values: List[float]) -> bytes:
    data = b"".join(float_to_gds_real(v) for v in values)
    return pack_record(record_type, DataType.REAL64, data)


def pack_ascii(record_type: int, text: str) -> bytes:
    encoded = text.encode("ascii")
    # GDS strings must be even length (pad with NUL if necessary)
    if len(encoded) % 2 != 0:
        encoded = encoded + b"\x00"
    return pack_record(record_type, DataType.ASCII, encoded)


def pack_bitarray(record_type: int, value: int) -> bytes:
    data = struct.pack(">H", value)
    return pack_record(record_type, DataType.BITARRAY, data)


# ---------------------------------------------------------------------------
# Record parsing
# ---------------------------------------------------------------------------

class GDSRecord:
    """A single parsed GDS-II record."""

    __slots__ = ("record_type", "data_type", "data")

    def __init__(self, record_type: int, data_type: int, data: bytes) -> None:
        self.record_type = record_type
        self.data_type = data_type
        self.data = data

    def as_int16_list(self) -> List[int]:
        n = len(self.data) // 2
        return list(struct.unpack(f">{n}h", self.data))

    def as_int32_list(self) -> List[int]:
        n = len(self.data) // 4
        return list(struct.unpack(f">{n}i", self.data))

    def as_real64_list(self) -> List[float]:
        n = len(self.data) // 8
        return [gds_real_to_float(self.data[i*8:(i+1)*8]) for i in range(n)]

    def as_string(self) -> str:
        return self.data.rstrip(b"\x00").decode("ascii")

    def as_bitarray(self) -> int:
        return struct.unpack(">H", self.data)[0]

    def __repr__(self) -> str:
        return (
            f"GDSRecord(type=0x{self.record_type:02X}, "
            f"dtype=0x{self.data_type:02X}, len={len(self.data)})"
        )


def iter_records(data: bytes):
    """Iterate over all GDS-II records in a byte buffer."""
    pos = 0
    while pos < len(data):
        if pos + 4 > len(data):
            raise ValueError(f"Truncated GDS-II record header at offset {pos}")
        length, record_type, data_type = struct.unpack_from(">HBB", data, pos)
        if length < 4:
            raise ValueError(f"Invalid record length {length} at offset {pos}")
        payload_len = length - 4
        if pos + length > len(data):
            raise ValueError(
                f"Record at offset {pos} claims {length} bytes but only "
                f"{len(data) - pos} remain"
            )
        payload = data[pos + 4: pos + length]
        yield GDSRecord(record_type, data_type, payload)
        pos += length

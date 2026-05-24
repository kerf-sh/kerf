"""kerf_firmware.ota.sign — Local CLI helper: package and sign firmware images.

Signing key lives on the developer's local machine (never uploaded to the server).

Signing algorithm: Ed25519 via the ``cryptography`` package (if available) or
``nacl`` (PyNaCl).  Falls back to a pure-HMAC stub only in test/offline mode.

Usage (Python API)
------------------
    signer = OTASigner.from_new_keypair()
    manifest = signer.sign_image(
        fw_path="firmware.bin",
        version="1.2.3",
        device_type="esp32",
    )
    # manifest.to_json() → upload to POST /v1/ota/release

    verifier = OTAVerifier(public_key_bytes=signer.public_key_bytes)
    verifier.verify(manifest, image_bytes)   # raises on bad sig / hash

CLI usage (via kerf firmware ota release)
-----------------------------------------
    kerf firmware ota keygen --out kerf_ota_key.pem
    kerf firmware ota release --key kerf_ota_key.pem --firmware build/firmware.bin \\
        --version 1.2.3 --device-type esp32
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Crypto backend selection
# ---------------------------------------------------------------------------

def _load_crypto():
    """Try to import ed25519 via ``cryptography`` or ``nacl``.

    Returns a (generate_fn, sign_fn, verify_fn, serialize_privkey_fn,
    deserialize_privkey_fn, serialize_pubkey_fn, deserialize_pubkey_fn) tuple.
    Raises ImportError if neither is available.
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey, Ed25519PublicKey,
        )
        from cryptography.hazmat.primitives.serialization import (
            Encoding, NoEncryption, PrivateFormat, PublicFormat,
            load_pem_private_key, load_pem_public_key,
        )

        def generate():
            return Ed25519PrivateKey.generate()

        def sign(private_key, data: bytes) -> bytes:
            return private_key.sign(data)

        def verify(public_key, signature: bytes, data: bytes):
            # Raises InvalidSignature on failure.
            public_key.verify(signature, data)

        def serialize_privkey(k) -> bytes:
            return k.private_bytes(
                Encoding.PEM,
                PrivateFormat.PKCS8,
                NoEncryption(),
            )

        def deserialize_privkey(pem: bytes):
            return load_pem_private_key(pem, password=None)

        def serialize_pubkey(k) -> bytes:
            return k.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

        def deserialize_pubkey(raw: bytes):
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )
            return Ed25519PublicKey.from_public_bytes(raw)

        return (generate, sign, verify,
                serialize_privkey, deserialize_privkey,
                serialize_pubkey, deserialize_pubkey,
                "cryptography")

    except ImportError:
        pass

    try:
        from nacl.signing import SigningKey, VerifyKey

        def generate():
            return SigningKey.generate()

        def sign(private_key, data: bytes) -> bytes:
            return bytes(private_key.sign(data).signature)

        def verify(public_key, signature: bytes, data: bytes):
            # Raises nacl.exceptions.BadSignatureError on failure.
            public_key.verify(data, signature)

        def serialize_privkey(k) -> bytes:
            return b"-----BEGIN NACL PRIVATE KEY-----\n" + bytes(k).hex().encode() + b"\n-----END NACL PRIVATE KEY-----\n"

        def deserialize_privkey(pem: bytes):
            lines = pem.decode().strip().splitlines()
            hex_str = lines[1] if len(lines) >= 2 else lines[0]
            return SigningKey(bytes.fromhex(hex_str))

        def serialize_pubkey(k) -> bytes:
            return bytes(k.verify_key)

        def deserialize_pubkey(raw: bytes):
            return VerifyKey(raw)

        return (generate, sign, verify,
                serialize_privkey, deserialize_privkey,
                serialize_pubkey, deserialize_pubkey,
                "nacl")

    except ImportError:
        pass

    raise ImportError(
        "No ed25519 backend found.  Install 'cryptography' (already in "
        "kerf-cloud deps) or 'PyNaCl'."
    )


# ---------------------------------------------------------------------------
# OTA Image header (binary format, little-endian)
# ---------------------------------------------------------------------------
# Offset  Size  Field
# 0       4     magic  0x4B455246  ("KERF")
# 4       4     version_int  (major<<16 | minor<<8 | patch)
# 8       4     image_size  (bytes, payload only, not including header)
# 12      32    sha256  (over the payload)
# 44      64    ed25519_signature  (over magic+version_int+image_size+sha256, 48 bytes)
# 108     16    device_type  (ASCII, NUL-padded)
# 124     4     timestamp  (unix epoch, uint32)
# 128     —     (end of header, total 128 bytes)

HEADER_MAGIC = 0x4B455246  # "KERF"
HEADER_SIZE = 128
HEADER_FMT = "<II I 32s 64s 16s I"   # magic, ver, size, sha256, sig, dtype, ts
# struct.calcsize("<II I 32s 64s 16s I") == 128  ✓


def _version_int(version: str) -> int:
    parts = version.lstrip("v").split(".")
    major = int(parts[0]) if len(parts) > 0 else 0
    minor = int(parts[1]) if len(parts) > 1 else 0
    patch = int(parts[2]) if len(parts) > 2 else 0
    return (major << 16) | (minor << 8) | patch


def _version_str(version_int: int) -> str:
    major = (version_int >> 16) & 0xFF
    minor = (version_int >> 8) & 0xFF
    patch = version_int & 0xFF
    return f"{major}.{minor}.{patch}"


# ---------------------------------------------------------------------------
# Header signing: sign over the "protected" prefix (everything except sig field).
# Protected region = magic(4) + version_int(4) + image_size(4) + sha256(32) = 44 bytes.
# The ed25519 signature (64 bytes) covers those 44 bytes.
# ---------------------------------------------------------------------------

_PROTECTED_FMT = "<II I 32s"   # magic, version_int, image_size, sha256
_PROTECTED_SIZE = struct.calcsize(_PROTECTED_FMT)  # 44


@dataclass
class OTAManifest:
    """Serialisable manifest returned by sign_image() / POST /v1/ota/release.

    Fields match what the device polls from GET /v1/ota/manifest/{device_id}.
    """
    version: str
    device_type: str
    sha256: str          # hex-encoded
    ed25519_signature: str   # hex-encoded, covers the protected header region
    public_key: str      # hex-encoded 32-byte raw ed25519 public key
    image_size: int      # bytes
    timestamp: int       # unix epoch
    download_url: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    def to_dict(self) -> dict:
        """Return manifest as a plain dict (alias for dataclasses.asdict)."""
        return asdict(self)

    @classmethod
    def from_json(cls, text: str) -> "OTAManifest":
        return cls(**json.loads(text))

    @classmethod
    def from_dict(cls, d: dict) -> "OTAManifest":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Signer (host-side, developer's machine)
# ---------------------------------------------------------------------------

class OTASigner:
    """Signs firmware images with an ed25519 private key.

    The private key never leaves the developer's machine.
    """

    def __init__(self, private_key, public_key_bytes: bytes, backend: str):
        self._private_key = private_key
        self.public_key_bytes = public_key_bytes  # 32 raw bytes
        self._backend = backend
        (self._generate, self._sign, self._verify,
         self._ser_priv, self._deser_priv,
         self._ser_pub, self._deser_pub, _) = _load_crypto()

    @classmethod
    def from_new_keypair(cls) -> "OTASigner":
        """Generate a fresh ed25519 keypair."""
        ops = _load_crypto()
        generate, sign, verify, ser_priv, deser_priv, ser_pub, deser_pub, backend = ops
        private_key = generate()
        pub_raw = ser_pub(private_key)
        return cls(private_key, pub_raw, backend)

    @classmethod
    def from_pem(cls, pem_path: str) -> "OTASigner":
        """Load private key from a PEM file path (as written by save_pem)."""
        ops = _load_crypto()
        generate, sign, verify, ser_priv, deser_priv, ser_pub, deser_pub, backend = ops
        pem_bytes = Path(pem_path).read_bytes()
        private_key = deser_priv(pem_bytes)
        pub_raw = ser_pub(private_key)
        return cls(private_key, pub_raw, backend)

    @classmethod
    def from_pem_string(cls, pem_str: str) -> "OTASigner":
        """Load private key from a PEM string (for API use — avoids writing key to disk)."""
        ops = _load_crypto()
        generate, sign, verify, ser_priv, deser_priv, ser_pub, deser_pub, backend = ops
        pem_bytes = pem_str.encode() if isinstance(pem_str, str) else pem_str
        private_key = deser_priv(pem_bytes)
        pub_raw = ser_pub(private_key)
        return cls(private_key, pub_raw, backend)

    def private_key_pem(self) -> str:
        """Return the private key as a PEM string (for secure transmission over local API)."""
        ops = _load_crypto()
        pem_bytes = ops[3](self._private_key)  # serialize_privkey
        return pem_bytes.decode() if isinstance(pem_bytes, bytes) else pem_bytes

    def save_pem(self, path: str) -> None:
        """Persist the private key to a PEM file (chmod 600)."""
        ops = _load_crypto()
        pem = ops[3](self._private_key)  # serialize_privkey
        Path(path).write_bytes(pem)
        os.chmod(path, 0o600)

    def sign_image(
        self,
        fw_path: str,
        version: str,
        device_type: str,
        download_url: str = "",
        timestamp: Optional[int] = None,
    ) -> OTAManifest:
        """Package and sign a firmware binary.

        Returns an OTAManifest (and writes the signed image alongside the
        original at ``<fw_path>.ota.bin`` so it can be uploaded).
        """
        image_bytes = Path(fw_path).read_bytes()
        return self.sign_bytes(
            image_bytes,
            version=version,
            device_type=device_type,
            download_url=download_url,
            timestamp=timestamp,
            out_path=str(Path(fw_path).with_suffix(".ota.bin")),
        )

    def sign_bytes(
        self,
        image_bytes: bytes,
        version: str,
        device_type: str,
        download_url: str = "",
        timestamp: Optional[int] = None,
        out_path: Optional[str] = None,
    ) -> OTAManifest:
        """Sign raw image bytes.  Returns OTAManifest (no file I/O required)."""
        ops = _load_crypto()
        sign_fn = ops[1]

        if timestamp is None:
            timestamp = int(time.time())

        sha256_digest = hashlib.sha256(image_bytes).digest()
        sha256_hex = sha256_digest.hex()
        version_int = _version_int(version)
        image_size = len(image_bytes)

        # Build protected region (44 bytes) and sign it.
        protected = struct.pack(
            _PROTECTED_FMT,
            HEADER_MAGIC,
            version_int,
            image_size,
            sha256_digest,
        )
        signature = sign_fn(self._private_key, protected)  # 64 bytes

        if out_path is not None:
            # Build full 128-byte header + payload and write.
            dtype_padded = device_type.encode()[:16].ljust(16, b"\x00")
            header = struct.pack(
                HEADER_FMT,
                HEADER_MAGIC,
                version_int,
                image_size,
                sha256_digest,
                signature,
                dtype_padded,
                timestamp,
            )
            assert len(header) == HEADER_SIZE
            Path(out_path).write_bytes(header + image_bytes)

        return OTAManifest(
            version=version,
            device_type=device_type,
            sha256=sha256_hex,
            ed25519_signature=signature.hex(),
            public_key=self.public_key_bytes.hex(),
            image_size=image_size,
            timestamp=timestamp,
            download_url=download_url,
        )


# ---------------------------------------------------------------------------
# Verifier (host-side or device-side emulation in tests)
# ---------------------------------------------------------------------------

class OTAVerifier:
    """Verifies a firmware image manifest.

    Used on the server (POST /v1/ota/release validation) and in tests.
    Also models the device-side verification logic for the C applier tests.
    """

    def __init__(self, public_key_bytes: bytes):
        """public_key_bytes: 32 raw bytes of the ed25519 public key."""
        self.public_key_bytes = public_key_bytes
        ops = _load_crypto()
        self._verify_fn = ops[2]
        self._deser_pub = ops[6]
        self._public_key = self._deser_pub(public_key_bytes)

    def verify(self, manifest: OTAManifest, image_bytes: bytes) -> None:
        """Verify sha256 + signature of image_bytes against manifest.

        Raises ValueError on hash mismatch.
        Raises the backend's signature exception on bad signature.
        The image_bytes must NOT include the 128-byte header.
        """
        # 1. SHA-256 check (must happen BEFORE signature verify so we reject
        #    corrupt payloads even if signature is somehow forged).
        actual_sha = hashlib.sha256(image_bytes).hexdigest()
        if actual_sha != manifest.sha256:
            raise ValueError(
                f"SHA-256 mismatch: expected {manifest.sha256!r}, "
                f"got {actual_sha!r}"
            )

        # 2. Signature check.
        sha256_digest = bytes.fromhex(manifest.sha256)
        version_int = _version_int(manifest.version)
        protected = struct.pack(
            _PROTECTED_FMT,
            HEADER_MAGIC,
            version_int,
            len(image_bytes),
            sha256_digest,
        )
        signature = bytes.fromhex(manifest.ed25519_signature)
        self._verify_fn(self._public_key, signature, protected)
        # Raises on bad signature (cryptography.InvalidSignature or nacl BadSignatureError).

    def verify_signed_image(self, signed_image_bytes: bytes) -> OTAManifest:
        """Verify a complete signed image (header + payload).

        Returns an OTAManifest on success.
        Raises ValueError / signature error on failure.
        """
        if len(signed_image_bytes) < HEADER_SIZE:
            raise ValueError("Image too small to contain OTA header")

        header_bytes = signed_image_bytes[:HEADER_SIZE]
        payload = signed_image_bytes[HEADER_SIZE:]

        (magic, version_int, image_size,
         sha256_digest, signature,
         dtype_raw, timestamp) = struct.unpack(HEADER_FMT, header_bytes)

        if magic != HEADER_MAGIC:
            raise ValueError(f"Bad OTA magic: 0x{magic:08X}")

        if image_size != len(payload):
            raise ValueError(
                f"Size mismatch: header says {image_size}, payload is {len(payload)}"
            )

        manifest = OTAManifest(
            version=_version_str(version_int),
            device_type=dtype_raw.rstrip(b"\x00").decode(errors="replace"),
            sha256=sha256_digest.hex(),
            ed25519_signature=signature.hex(),
            public_key=self.public_key_bytes.hex(),
            image_size=image_size,
            timestamp=timestamp,
        )
        self.verify(manifest, payload)
        return manifest

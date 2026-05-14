import os
import base64
import hashlib

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from config import get_settings


def _derive_key(domain: str) -> bytes:
    settings = get_settings()
    key_material = b"kerf:enc:" + domain.encode() + b":" + settings.jwt_secret.encode()
    return hashlib.sha256(key_material).digest()


def encrypt_secret(plaintext: bytes, domain: str) -> bytes:
    nonce = os.urandom(12)
    key = _derive_key(domain)
    aesgcm = AESGCM(key)
    ciphertext_and_tag = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext_and_tag


def decrypt_secret(blob: bytes, domain: str) -> bytes:
    nonce = blob[:12]
    ciphertext_and_tag = blob[12:]
    key = _derive_key(domain)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext_and_tag, None)

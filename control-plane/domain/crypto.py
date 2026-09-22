"""Verdent Platform — AES-256-GCM encryption-at-rest helpers.

Secrets like Cloudflare API tokens are encrypted at rest with the key in
`CLOUDFLARE_TOKEN_ENCRYPTION_KEY` (base64, decoding to exactly 32 bytes).
Ciphertext format: `base64(nonce || ciphertext || tag)`.
"""

import base64
import os

from cryptography import exceptions as crypto_exc
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from domain.security import sha256_hex


def _load_key(raw_key: str) -> bytes:
    raw = base64.b64decode(raw_key)
    if len(raw) != 32:
        raise ValueError("CLOUDFLARE_TOKEN_ENCRYPTION_KEY must decode to exactly 32 bytes")
    return raw


def encrypt_secret(plaintext: str, key_b64: str) -> str:
    key = _load_key(key_b64)
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_secret(ciphertext: str, key_b64: str) -> str:
    key = _load_key(key_b64)
    blob = base64.b64decode(ciphertext)
    nonce, ct = blob[:12], blob[12:]
    pt = AESGCM(key).decrypt(nonce, ct, None)
    return pt.decode("utf-8")


def encrypt_fingerprint(ciphertext: str, key_b64: str) -> str:
    """Deterministic fingerprint of a ciphertext for lookups without decryption."""
    try:
        decrypt_secret(ciphertext, key_b64)
        return sha256_hex("ok")
    except crypto_exc.InvalidTag:
        return sha256_hex("invalid")

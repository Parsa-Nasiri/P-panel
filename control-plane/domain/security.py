"""Verdent Platform — hashing & HMAC helpers (no secrets in the data plane).

Node ingest auth (Document 5):
- At provisioning, a random secret is generated per Node. The Control Plane
  stores `H = sha256(secret + NODE_HMAC_SECRET_PEPPER)` in
  `nodes.node_secret_hash` and mirrors `H` into the Node's own KV.
- The Node signs every ingest/health request:
      signature = hex(hmac_sha256(H, `${nodeId}.${timestamp}.${nonce}.${body}`))
- The Control Plane verifies using `node_secret_hash` (it holds H), checks
  the timestamp window, and enforces nonce uniqueness per Node+window.

Result: a compromised Node can forge usage/health reports only for itself —
never for another Node, never against the Control Plane's own API tokens.
"""

import hashlib
import hmac
import time

from domain.config import settings

SIGNATURE_TTL_SECONDS = 120


def sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def derive_node_secret_hash(secret: str) -> str:
    """H = sha256(secret + pepper) — stored both in Postgres and Node KV."""
    return sha256_hex(secret + settings.node_hmac_secret_pepper)


def compute_expected_signature(node_secret_hash: str, node_id: str, timestamp: str, nonce: str, body: bytes) -> str:
    mac = hmac.new(
        node_secret_hash.encode("utf-8"),
        f"{node_id}.{timestamp}.{nonce}.".encode("utf-8") + body,
        hashlib.sha256,
    )
    return mac.hexdigest()


def secure_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def timestamp_within_window(timestamp_ms: str) -> bool:
    try:
        ts = int(timestamp_ms) / 1000.0
    except (TypeError, ValueError):
        return False
    return abs(time.time() - ts) <= SIGNATURE_TTL_SECONDS

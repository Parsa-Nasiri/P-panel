"""One-off: control-plane smoke test (no database required).

1. import api.main (FastAPI app wiring)
2. crypto round-trip: node provisioning -> payload signing -> server verify
3. Alembic migration content markers
4. Phase 1-5 logic: naming, RBAC, gaming honesty guard, subscription render
5. full bot dispatcher wiring
"""

import sys
import os
import time
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("TELEGRAM_OWNER_ID", "123456789")
os.environ.setdefault("NODE_HMAC_SECRET_PEPPER", "test-pepper")

# 1. app import
from api.main import app  # noqa: E402

routes = set()
def _walk(r):
    for route in r.routes:
        p = getattr(route, "path", None)
        if p:
            routes.add(p)
        inner = getattr(route, "original_router", None)
        if inner is not None:
            for sub in inner.routes:
                if hasattr(sub, "path"):
                    routes.add(sub.path)

_walk(app.router)
print("app import OK; routes:", sorted(routes))

assert "/health" in routes
assert "/internal/nodes/{node_id}/usage" in routes
assert "/internal/nodes/{node_id}/health" in routes
assert "/s/{subscription_token}" in routes
assert "/webhook/{secret_token}" in routes
print("route presence: PASS")

# 2. crypto round-trip
from domain.security import (
    compute_expected_signature,
    derive_node_secret_hash,
    secure_compare,
    timestamp_within_window,
)

node_id = str(uuid.uuid4())
provisioning_secret = uuid.uuid4().hex
node_secret_hash = derive_node_secret_hash(provisioning_secret)

payload = (
    '{"configId": "%s", "connectionId": "conn-1", "sequenceNumber": 1,'
    ' "bytesUp": 1024, "bytesDown": 4096,'
    ' "windowStartedAt": "2026-09-21T18:00:00Z", "reportedAt": "2026-09-21T18:00:30Z"}'
    % str(uuid.uuid4())
).encode()

ts = str(int(time.time() * 1000))
nonce = uuid.uuid4().hex
sig = compute_expected_signature(node_secret_hash, node_id, ts, nonce, payload)

ok = secure_compare(compute_expected_signature(node_secret_hash, node_id, ts, nonce, payload), sig)
tampered = payload[:-6] + b'"ZZZ"}'
ok2 = not secure_compare(compute_expected_signature(node_secret_hash, node_id, ts, nonce, tampered), sig)
print("crypto round-trip:", "PASS" if ok and ok2 and timestamp_within_window(ts) else "FAIL")

# 3. migration markers
mig = open(os.path.join("db", "migrations", "versions", "001_initial.py"), encoding="utf-8").read()
print("migration markers:", "PASS" if mig.count("CREATE TABLE") == 21 and "trg_usage_events_aggregate" in mig else "FAIL")

# 4. Phase 1-5 logic
from domain.naming import validate_display_name, mint_suffix

assert validate_display_name("Parsa12")
assert validate_display_name("پارسا۱۲")
assert not validate_display_name("has space")
assert not validate_display_name("x" * 21)
assert len(mint_suffix()) == 5 and mint_suffix().isalnum()
print("naming: PASS")

from domain.rbac import (
    ROLE_SUPPORT, ROLE_INFRASTRUCTURE, ROLE_ADMIN,
    PERM_PAYMENT_REVIEW, PERM_NODE_MANAGE, PERM_ADMIN_MANAGE,
    permissions_for, role_has_permission,
)

assert PERM_PAYMENT_REVIEW in permissions_for(ROLE_SUPPORT)
assert PERM_NODE_MANAGE not in permissions_for(ROLE_SUPPORT)
assert PERM_NODE_MANAGE in permissions_for(ROLE_INFRASTRUCTURE)
assert PERM_ADMIN_MANAGE not in permissions_for(ROLE_ADMIN)  # OWNER-only
assert "admin.manage" in permissions_for("OWNER")
assert not role_has_permission(ROLE_SUPPORT, PERM_ADMIN_MANAGE)
print("rbac: PASS")

from domain.gaming import validate_settings

assert validate_settings({"mtu_hint": 1280, "doh_endpoint": "https://x"}) == []
assert validate_settings({"udp_enabled": True}) != []
assert validate_settings({"ping_reduction": 20}) != []
print("gaming honesty guard: PASS")

from domain.subscriptions import render_vless_uri, build_subscription_body

uri = render_vless_uri("https://node1.example.workers.dev", "3f2504e0-4f89-11d3-9a0c-0305e82c3301", "Parsa")
assert uri.startswith("vless://3f2504e0-4f89-11d3-9a0c-0305e82c3301@node1.example.workers.dev:443")
assert "path=%2Fvl" in uri and "security=tls" in uri
body = build_subscription_body([uri])
import base64
assert uri in base64.b64decode(body).decode()
print("subscription render: PASS")

from domain.provisioning import derive_secure_path

sp1, sp2 = derive_secure_path("a"), derive_secure_path("b")
assert sp1 != sp2 and len(sp1) == 24 and derive_secure_path("a") == sp1
print("secure path derivation: PASS")

from domain.cloudflare import CloudflareClient
from domain.crypto import encrypt_secret

import base64 as _b64
_key_b64 = _b64.b64encode(os.urandom(32)).decode()
_token = "cf-test-token"
_token_encrypted_bytes = encrypt_secret(_token, _key_b64).encode("ascii")  # LargeBinary storage form
_client = CloudflareClient(_token_encrypted_bytes, _key_b64, "acct123")
assert _client._headers["Authorization"] == f"Bearer {_token}"
assert _client._account_id == "acct123"
print("cloudflare client construct + decrypt: PASS")

# 5. bot dispatcher
import bot.router  # noqa: E402, F401  (registers handlers + includes into dp)
from bot.webhook import dp

print("bot dispatcher:", "PASS" if len(dp.sub_routers) > 0 else "FAIL")

print("\nALL SMOKE TESTS DONE")

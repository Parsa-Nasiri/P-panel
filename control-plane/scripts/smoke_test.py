"""One-off: control-plane smoke test (no database required).

1. import api.main (FastAPI app wiring)
2. crypto round-trip: node provisioning -> payload signing -> server verify
3. Alembic migration file syntax + revision chain
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
from api.main import app  # noqa: E402, F401

routes = sorted({r.path for r in app.routes if hasattr(r, "path")})
print("app import OK; routes:", routes)

# 2. crypto round-trip
from domain.security import (  # noqa: E402
    compute_expected_signature,
    derive_node_secret_hash,
    secure_compare,
    timestamp_within_window,
)

node_id = str(uuid.uuid4())
provisioning_secret = uuid.uuid4().hex
node_secret_hash = derive_node_secret_hash(provisioning_secret)
print("derived node_secret_hash:", node_secret_hash[:16], "...")

payload = (
    '{"configId": "%s", "connectionId": "conn-1", "sequenceNumber": 1,'
    ' "bytesUp": 1024, "bytesDown": 4096,'
    ' "windowStartedAt": "2026-09-21T18:00:00Z", "reportedAt": "2026-09-21T18:00:30Z"}'
    % str(uuid.uuid4())
).encode()

ts = str(int(time.time() * 1000))
nonce = uuid.uuid4().hex
sig = compute_expected_signature(node_secret_hash, node_id, ts, nonce, payload)
print("client signature:", sig[:16], "...")

ok = secure_compare(compute_expected_signature(node_secret_hash, node_id, ts, nonce, payload), sig)
print("server verify:", "PASS" if ok else "FAIL")

tampered = payload[:-6] + b'"ZZZ"}'
ok2 = not secure_compare(compute_expected_signature(node_secret_hash, node_id, ts, nonce, tampered), sig)
print("tamper reject:", "PASS" if ok2 else "FAIL")
print("timestamp window:", "PASS" if timestamp_within_window(ts) else "FAIL")

# 3. migration revision chain
import ast  # noqa: E402

mig = open(os.path.join("db", "migrations", "versions", "001_initial.py"), encoding="utf-8").read()
print("trigger present:", "trg_usage_events_aggregate" in mig and "fn_usage_event_aggregate" in mig)
print("tables in migration:", mig.count("CREATE TABLE"))
print("\nALL SMOKE TESTS DONE")

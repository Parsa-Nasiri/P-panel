"""Verdent Platform — node provisioning automation (Phase 2).

One function per lifecycle step, each auditable and idempotent where the
Cloudflare API allows:

  provision_node      — add a Node: KV namespace + worker upload + subdomain
  decommission_node   — delete the script, mark DECOMMISSIONED (assignments
                        are revoked first by the caller)

The worker bundle is the control plane's own copy (assets/worker_bundle.js),
synced from node-worker/dist/worker.js by scripts/sync_worker_bundle.py.
"""

import json
import logging
import secrets
import uuid as uuid_lib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import CloudflareAccount, Node
from domain.cloudflare import CloudflareClient
from domain.config import settings
from domain.kv_sync import seed_node_kv
from domain.security import derive_node_secret_hash

logger = logging.getLogger("verdent.provisioning")


class ProvisioningError(Exception):
    pass


def _load_bundle() -> str:
    path = Path(settings.node_worker_bundle_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    if not path.exists():
        raise ProvisioningError(
            f"worker bundle missing at {path} — run scripts/sync_worker_bundle.py after building node-worker"
        )
    return path.read_text(encoding="utf-8")


def derive_secure_path(node_id: str) -> str:
    """Deterministic secret path segment for the node's DoH/health routes.

    Re-derivable by the control plane at any time (health loop needs it) —
    no extra column on the fixed schema.
    """
    import hashlib

    raw = hashlib.sha256(f"{node_id}:{settings.node_hmac_secret_pepper}".encode()).hexdigest()
    return raw[:24]


async def provision_node(
    db: AsyncSession,
    cloudflare_account_id: str,
    worker_script_name: str,
    capability_tags: list[str] | None = None,
    max_assignment_count: int = 3,
) -> Node:
    account = (
        await db.execute(
            select(CloudflareAccount).where(CloudflareAccount.id == cloudflare_account_id)
        )
    ).scalar_one_or_none()

    if account is None:
        raise ProvisioningError("cloudflare account not found")

    client = CloudflareClient(
        account.api_token_encrypted,
        settings.cloudflare_token_encryption_key,
        account.cf_account_id,
    )

    node_id = str(uuid_lib.uuid4())

    # 1. KV namespace (the node's only storage)
    ns_title = f"verdent-node-{worker_script_name}"
    try:
        namespace_id = await client.create_kv_namespace(ns_title)
    except Exception as exc:  # noqa: BLE001
        raise ProvisioningError(f"KV namespace creation failed: {exc}") from exc

    # 2. Node secret: random, hashed with the platform pepper; the HASH is
    #    both the HMAC verification key (stored here + mirrored to node KV).
    node_secret = secrets.token_hex(32)
    node_secret_hash = derive_node_secret_hash(node_secret)

    # 3. Provisioned settings embed (Document 1/5: no admin credentials in the
    #    data plane, ever)
    provisioned = {
        "nodeId": node_id,
        "verdentUrl": settings.subscription_base_url or "",
        "securePath": derive_secure_path(node_id),
        "mainDomain": "",  # filled from the workers.dev URL after enabling
        "proxyIpMode": "proxyip",
        "proxyIPs": [],
        "prefixes": [],
        "fallback": "",
        "dohUrl": "",
    }

    # 4. Upload the forked bundle + enable the public subdomain
    try:
        bundle = _load_bundle()
        await client.upload_worker_script(
            worker_script_name,
            bundle,
            json.dumps(provisioned, ensure_ascii=False),
            namespace_id,
            settings.nodes_enable_durable_objects,
        )
        public_url = await client.enable_workers_dev(worker_script_name)
    except Exception as exc:  # noqa: BLE001
        raise ProvisioningError(f"worker upload failed: {exc}") from exc

    # 5. Seed KV + persist the node row
    try:
        await seed_node_kv(client, namespace_id, node_secret_hash)
    except Exception as exc:  # noqa: BLE001
        raise ProvisioningError(f"KV seed failed: {exc}") from exc

    node = Node(
        id=node_id,
        cloudflare_account_id=cloudflare_account_id,
        worker_script_name=worker_script_name,
        custom_domain=public_url,
        capability_tags=capability_tags or ["general", "doh"],
        control_plane_health=False,
        data_plane_health=False,
        health_score=0,
        max_assignment_count=max_assignment_count,
        node_secret_hash=node_secret_hash,
        state="PROVISIONING",
    )
    db.add(node)
    await db.commit()

    logger.info("provisioned node %s at %s", node_id, public_url)
    return node


async def decommission_node(db: AsyncSession, node: Node) -> None:
    account = (
        await db.execute(
            select(CloudflareAccount).where(
                CloudflareAccount.id == node.cloudflare_account_id
            )
        )
    ).scalar_one_or_none()

    if account is not None:
        client = CloudflareClient(
            account.api_token_encrypted,
            settings.cloudflare_token_encryption_key,
            account.cf_account_id,
        )
        try:
            await client.delete_worker_script(node.worker_script_name or "")
        except Exception:  # noqa: BLE001
            logger.exception("worker delete failed for %s (continuing)", node.id)

    node.state = "DECOMMISSIONED"
    node.current_assignment_count = 0
    await db.commit()

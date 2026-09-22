"""Verdent Platform — the credential map sync (Document 1/3 §K #5).

The Node's KV `proxyUsers` map is the single source of proxy credentials.
Every mutation flows through here:
    sync_assignment   → mint/refresh one entry (vl:<uuid> or tr:<hash>)
    disable_entry     → flip status to "disabled" (revocation, quota, expiry)
    remove_entry      → delete the key entirely

KV writes go through the Cloudflare API with the NODE's account token. The
Node reads with a 30s cache — propagation latency is bounded by that.
"""

import hashlib
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import CloudflareAccount, Configuration, Node
from domain.config import settings
from domain.cloudflare import CloudflareClient

logger = logging.getLogger("verdent.provisioning")

PROXY_USERS_KEY = "proxyUsers"
NODE_SECRET_KEY = "nodeSecret"


def vless_key(proxy_uuid: str) -> str:
    return f"vl:{proxy_uuid}"


def trojan_key(password: str) -> str:
    return f"tr:{hashlib.sha224(password.encode()).hexdigest()}"


async def get_node_kv_writer(db: AsyncSession, node: Node) -> tuple[CloudflareClient, str] | None:
    """Build a CloudflareClient for the node's account + its KV namespace id.

    The KV namespace id is not stored in the nodes table (schema is fixed) —
    it is recoverable from the account's namespace list by title convention
    `verdent-node-<worker_script_name>`. Cached per call; fine at Phase-2
    scale (a handful of writes per provisioning event).
    """
    account = (
        await db.execute(
            select(CloudflareAccount).where(
                CloudflareAccount.id == node.cloudflare_account_id
            )
        )
    ).scalar_one_or_none()

    if account is None:
        logger.error("node %s has no cloudflare account", node.id)
        return None

    return CloudflareClient(
        account.api_token_encrypted,
        settings.cloudflare_token_encryption_key,
        account.cf_account_id,
    ), f"verdent-node-{node.worker_script_name or node.id[:8]}"


async def _find_namespace_id(client: CloudflareClient, title: str) -> str | None:
    import httpx

    url = f"https://api.cloudflare.com/client/v4/accounts/{client._account_id}/storage/kv/namespaces?per_page=100"
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.get(url, headers=client._headers)
    data = resp.json()
    if not data.get("success"):
        return None
    for ns in data.get("result", []):
        if ns.get("title") == title:
            return ns["id"]
    return None


async def _read_map(client: CloudflareClient, ns_id: str) -> dict:
    import httpx

    url = f"https://api.cloudflare.com/client/v4/accounts/{client._account_id}/storage/kv/namespaces/{ns_id}/values/{PROXY_USERS_KEY}"
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.get(url, headers=client._headers)
    if resp.status_code == 404:
        return {}
    try:
        return resp.json()
    except Exception:  # noqa: BLE001
        return {}


async def _write_map(client: CloudflareClient, ns_id: str, mapping: dict) -> None:
    await client.put_kv_value(ns_id, PROXY_USERS_KEY, json.dumps(mapping, ensure_ascii=False))


async def sync_assignment(
    db: AsyncSession,
    node: Node,
    *,
    proxy_uuid: str,
    config_id: str,
    status: str = "active",
    device_limit: int = 1,
) -> bool:
    """Upsert one credential entry on the node. Returns success."""
    writer = await get_node_kv_writer(db, node)
    if writer is None:
        return False
    client, ns_title = writer
    ns_id = await _find_namespace_id(client, ns_title)
    if ns_id is None:
        logger.error("KV namespace %s not found for node %s", ns_title, node.id)
        return False

    mapping = await _read_map(client, ns_id)
    mapping[vless_key(proxy_uuid)] = {
        "configId": config_id,
        "status": status,
        "deviceLimit": device_limit,
    }
    await _write_map(client, ns_id, mapping)
    return True


async def set_entry_status(
    db: AsyncSession,
    node: Node,
    proxy_uuid: str,
    status: str,
) -> bool:
    writer = await get_node_kv_writer(db, node)
    if writer is None:
        return False
    client, ns_title = writer
    ns_id = await _find_namespace_id(client, ns_title)
    if ns_id is None:
        return False

    mapping = await _read_map(client, ns_id)
    key = vless_key(proxy_uuid)
    if key in mapping:
        mapping[key]["status"] = status
        await _write_map(client, ns_id, mapping)
    return True


async def seed_node_kv(
    client: CloudflareClient,
    namespace_id: str,
    node_secret_hash: str,
) -> None:
    """Fresh-node KV seed: verification key + empty credential map."""
    await client.put_kv_value(namespace_id, NODE_SECRET_KEY, node_secret_hash)
    await client.put_kv_value(namespace_id, PROXY_USERS_KEY, "{}")

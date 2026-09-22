"""Verdent Platform — Cloudflare API client (Phase 2).

Minimal, scoped to exactly what provisioning needs:
- create a KV namespace
- upload the forked worker bundle (multipart module upload)
- enable the workers.dev subdomain
- read/write KV values (proxyUsers map, nodeSecret)

Auth: the account's API token, stored AES-256-GCM-encrypted at rest
(cloudflare_accounts.api_token_encrypted) — never in the data plane.
Deliberately NO zone-level operations: workers.dev subdomains need no DNS
control, which keeps the required token scope minimal.
"""

import base64
import logging
from typing import Any

import httpx

from domain.crypto import decrypt_secret

logger = logging.getLogger("verdent.cloudflare")

CF_API_BASE = "https://api.cloudflare.com/client/v4"


class CloudflareError(Exception):
    pass


def _auth_headers(api_token_encrypted: bytes, key_b64: str) -> dict[str, str]:
    # api_token_encrypted is the ASCII of the base64 ciphertext (LargeBinary)
    token = decrypt_secret(api_token_encrypted.decode("ascii"), key_b64)
    return {"Authorization": f"Bearer {token}"}


def _check(resp_json: dict[str, Any], what: str) -> dict[str, Any]:
    if not resp_json.get("success"):
        errors = "; ".join(str(e.get("message", e)) for e in resp_json.get("errors", []))
        raise CloudflareError(f"{what} failed: {errors}")
    return resp_json.get("result", {})


class CloudflareClient:
    def __init__(self, api_token_encrypted: bytes, encryption_key_b64: str, account_id: str):
        self._headers = _auth_headers(api_token_encrypted, encryption_key_b64)
        self._account_id = account_id

    async def _request(self, method: str, path: str, *, json_body: Any = None, content: Any = None, data: Any = None, files: Any = None, headers: dict | None = None) -> dict[str, Any]:
        url = f"{CF_API_BASE}{path}"
        merged = {**self._headers, **(headers or {})}
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.request(method, url, json=json_body, content=content, data=data, files=files, headers=merged)
        if resp.status_code >= 400:
            raise CloudflareError(f"{method} {path} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    # -- KV ---------------------------------------------------------------

    async def create_kv_namespace(self, title: str) -> str:
        result = _check(
            await self._request(
                "POST", f"/accounts/{self._account_id}/storage/kv/namespaces",
                json_body={"title": title},
            ),
            "create KV namespace",
        )
        return result["id"]

    async def put_kv_value(self, namespace_id: str, key: str, value: str) -> None:
        await self._request(
            "PUT",
            f"/accounts/{self._account_id}/storage/kv/namespaces/{namespace_id}/values/{key}",
            content=value.encode("utf-8"),
            headers={"Content-Type": "text/plain"},
        )

    # -- Workers -----------------------------------------------------------

    async def upload_worker_script(
        self,
        script_name: str,
        worker_js: str,
        provisioned_json: str,
        kv_namespace_id: str,
        enable_durable_objects: bool,
    ) -> None:
        """Multipart module upload (Document 5: settings as a plain_text
        binding, KV binding for the credential map)."""
        metadata: dict[str, Any] = {
            "main_module": "worker.js",
            "compatibility_date": "2025-01-01",
            "compatibility_flags": ["nodejs_compat"],
            "bindings": [
                {"type": "plain_text", "name": "provisioned", "text": provisioned_json},
                {"type": "kv_namespace", "name": "kv", "namespace_id": kv_namespace_id},
            ],
        }

        if enable_durable_objects:
            # Requires Workers Paid. On free plans this binding is omitted and
            # the Node degrades to fail-open session checks.
            metadata["bindings"].append(
                {"type": "durable_object_namespace", "name": "SESSION_COUNTER", "class_name": "SessionCounter"}
            )
            metadata["migrations"] = {"new_tag": "v1", "new_classes": ["SessionCounter"]}

        import json as _json

        files = {
            "metadata": (None, _json.dumps(metadata), "application/json"),
            "worker.js": ("worker.js", worker_js, "application/javascript+module"),
        }

        result = await self._request(
            "PUT",
            f"/accounts/{self._account_id}/workers/scripts/{script_name}",
            files=files,
        )
        _check(result, "upload worker script")

    async def enable_workers_dev(self, script_name: str) -> str:
        """Enable the workers.dev subdomain and return the public URL."""
        result = _check(
            await self._request(
                "POST",
                f"/accounts/{self._account_id}/workers/scripts/{script_name}/subdomain",
                json_body={"enabled": True, "previews_enabled": False},
            ),
            "enable workers.dev subdomain",
        )
        subdomain = result.get("subdomain")
        if not subdomain:
            raise CloudflareError("workers.dev subdomain missing from response")
        return f"https://{script_name}.{subdomain}.workers.dev"

    async def delete_worker_script(self, script_name: str) -> None:
        await self._request("DELETE", f"/accounts/{self._account_id}/workers/scripts/{script_name}")

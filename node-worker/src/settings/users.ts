// Verdent fork: the multi-tenant credential lookup layer.
// Document 1, "BPB Fork Scope" #1 — replace the single vlUUID / Trojan
// password with a KV-backed map written exclusively by the Control Plane.

import { ProxyUser, ProxyUserMap } from '#types/settings';

export const PROXY_USERS_KEY = 'proxyUsers';
export const NODE_SECRET_KEY = 'nodeSecret';

// Single-flight cache per isolate: KV reads on every WS open are cheap, but
// the map only changes on provisioning/revocation events, so a short TTL
// bounds revocation latency without hammering KV on every connection.
const CACHE_TTL_MS = 30_000;
let cachedMap: ProxyUserMap | null = null;
let cachedAt = 0;

export async function getProxyUserMap(env: Env): Promise<ProxyUserMap> {
    const now = Date.now();

    if (cachedMap && now - cachedAt < CACHE_TTL_MS) {
        return cachedMap;
    }

    try {
        const map = await env.kv.get<ProxyUserMap>(PROXY_USERS_KEY, { type: 'json' });
        cachedMap = map ?? {};
        cachedAt = now;
        return cachedMap;
    } catch (error) {
        console.error('Failed to read proxyUsers from KV:', error);
        return cachedMap ?? {};
    }
}

export async function getUserByUuid(env: Env, uuid: string): Promise<ProxyUser | null> {
    const map = await getProxyUserMap(env);
    const user = map[`vl:${uuid}`] ?? null;
    return user && user.status === 'active' ? user : null;
}

export async function getUserByTrojanHash(env: Env, sha224Hex: string): Promise<ProxyUser | null> {
    const map = await getProxyUserMap(env);
    const user = map[`tr:${sha224Hex}`] ?? null;
    return user && user.status === 'active' ? user : null;
}

export async function getNodeSecret(env: Env): Promise<string | null> {
    try {
        return await env.kv.get(NODE_SECRET_KEY) ?? null;
    } catch (error) {
        console.error('Failed to read nodeSecret from KV:', error);
        return null;
    }
}

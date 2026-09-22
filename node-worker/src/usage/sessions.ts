// Verdent fork: concurrent-session admission via the SessionCounter Durable
// Object. Graceful degradation: if the SESSION_COUNTER binding is missing
// (e.g. a free-plan Node where DOs aren't available), the check is skipped
// with a one-time warning — the limit is then enforced only by the next
// paid-plan deployment. Flagged in the deployment guide.

import { SessionCounter } from '@usage/session-counter';

let warnedMissing = false;

export async function incrSession(
    env: Env,
    configId: string,
    deviceLimit: number,
    ctx: ExecutionContext
): Promise<boolean> {
    const namespace = (env as never as { SESSION_COUNTER?: DurableObjectNamespace }).SESSION_COUNTER;

    if (!namespace) {
        if (!warnedMissing) {
            warnedMissing = true;
            console.warn('SESSION_COUNTER binding missing — device limits not enforced on this Node');
        }
        return true;
    }

    const stub = namespace.get(namespace.idFromName(configId));
    const res = await stub.fetch('https://counter/incr', {
        method: 'POST',
        body: JSON.stringify({ configId, limit: deviceLimit })
    });

    if (!res.ok) {
        console.error('SessionCounter /incr failed:', res.status);
        return true; // fail-open on accounting error, never block the tunnel
    }

    const { allowed } = (await res.json()) as { allowed: boolean };
    return allowed;
}

export async function decrSession(env: Env, configId: string, ctx: ExecutionContext): Promise<void> {
    const namespace = (env as never as { SESSION_COUNTER?: DurableObjectNamespace }).SESSION_COUNTER;

    if (!namespace) return;

    const stub = namespace.get(namespace.idFromName(configId));
    ctx.waitUntil(
        stub.fetch('https://counter/decr', {
            method: 'POST',
            body: JSON.stringify({ configId })
        }).catch(error => console.error('SessionCounter /decr failed:', error))
    );
}

// Verdent fork: minimal internal health route.
// A cheap control-plane health signal (Document 1 §F): "the Worker exists and
// responds" — NOT a data-plane signal. Reachability is protected by the
// securePath (secret by design, derived from a UUID) — a judgment call,
// flagged in the deployment guide.

import { NODE_VERSION, getGlobals } from '@settings';

export async function renderHealth(): Promise<Response> {
    const { nodeId, mainDomain } = getGlobals();

    return Response.json({
        status: 'ok',
        node: nodeId,
        mainDomain,
        version: NODE_VERSION,
        checkedAt: new Date().toISOString()
    });
}

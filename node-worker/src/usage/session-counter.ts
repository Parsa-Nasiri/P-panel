// Verdent fork: concurrent-session admission check (Document 1, "BPB Fork
// Scope" #5; Document 3, §Device Limits).
// A Durable Object per Configuration gives single-writer strong consistency —
// closing the race where two near-simultaneous connections both pass a
// device-limit check before either write lands. Each new connection:
// increment-and-check; over the limit, refused with a client-recognizable
// close reason. On close: decrement.

export class SessionCounter {
    // In-memory state: single-object, single-threaded per Configuration name
    // (idFromName(configId)) — this IS the strong consistency primitive.
    private sessions: Map<string, number> = new Map();

    async fetch(request: Request): Promise<Response> {
        const url = new URL(request.url);

        try {
            if (request.method === 'POST' && url.pathname === '/incr') {
                const { configId, limit } = (await request.json()) as { configId: string, limit: number };
                const current = this.sessions.get(configId) ?? 0;
                const allowed = current < limit;

                if (allowed) {
                    this.sessions.set(configId, current + 1);
                }

                return Response.json({ allowed, count: allowed ? current + 1 : current });
            }

            if (request.method === 'POST' && url.pathname === '/decr') {
                const { configId } = (await request.json()) as { configId: string };
                const current = this.sessions.get(configId) ?? 0;
                const next = Math.max(0, current - 1);

                if (next === 0) {
                    this.sessions.delete(configId);
                } else {
                    this.sessions.set(configId, next);
                }

                return Response.json({ count: next });
            }

            if (request.method === 'GET' && url.pathname === '/count') {
                const configId = url.searchParams.get('configId') ?? '';
                return Response.json({ count: this.sessions.get(configId) ?? 0 });
            }

            return Response.json({ error: 'not found' }, { status: 404 });
        } catch (error) {
            return Response.json({ error: String(error) }, { status: 400 });
        }
    }
}

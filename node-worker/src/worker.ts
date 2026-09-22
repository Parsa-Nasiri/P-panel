import { handleDoH } from '@handlers/doh';
import { renderError } from '@handlers/error';
import { renderHealth } from '@usage/health';
import { fallback } from '@handlers/utils';
import { handleWebsocket } from '@handlers/websocket';
import { init, getGlobals } from '@settings';
import { SessionCounter } from '@usage/session-counter';

// Verdent fork of BPB v5.1.1 (Document 1, "BPB Fork Scope" #6 — subtraction,
// not addition): the customer-facing panel/login UI, the /sub serving
// responsibility (owned by the Control Plane), and the telegram hook are
// removed from the public build entirely. Every Node's public surface is
// exactly: WebSocket relay, DoH, and a minimal internal health route.

export default {
	async fetch(request: Request, env: Env, ctx: ExecutionContext) {
		try {
			init(request, env);
			if (request.headers.get('Upgrade') === 'websocket') return handleWebsocket(request, env, ctx);
			const { securePath, pathname } = getGlobals();
			const path = pathname.split('/').splice(0, 3).join('/');

			switch (path) {
				case `/${securePath}/dns-query`:
					return handleDoH(request);

				case `/${securePath}/health`:
					return renderHealth();

				default:
					return fallback(request);
			}
		} catch (error) {
			return renderError(error);
		}
	}
};

export { SessionCounter };

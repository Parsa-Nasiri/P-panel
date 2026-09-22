import { EmbededSettings, ReqSettings } from '#types/settings';

Object.assign(globalThis, {
    _VL_: atob('dmxlc3M='),
    _TR_: atob('dHJvamFu'),
    _project_SM_: atob('YnBi'),
});

// Verdent fork of BPB v5.1.1 settings layer (Document 1, "BPB Fork Scope"):
// - The single-tenant vlUUID / trojan password are gone. Proxy credentials now
//   live in a KV-backed map (`proxyUsers`, see settings/users.ts) written
//   exclusively by the Control Plane.
// - The embedded admin surface (accID / accEmail / accToken) is gone: a Node
//   never receives the credential that provisioned it (Document 5).
// - Provisioned static routing/DNS settings arrive as an `env.provisioned`
//   JSON string (script upload vars in both the manual and automated flows).

export const NODE_VERSION = '1.0.0';

export function init(request: Request, env: Env) {
    if (!env.provisioned) {
        throw new Error('Verdent Node is missing its provisioned settings (env.provisioned). Deploy via the Control Plane provisioning flow, or provision-manual.md.');
    }

    let provisioned: EmbededSettings;
    try {
        provisioned = JSON.parse(env.provisioned) as EmbededSettings;
    } catch (error) {
        throw new Error('env.provisioned is not valid JSON — refusing to start a mis-provisioned Node.');
    }

    const required: Array<keyof EmbededSettings> = [
        'nodeId', 'verdentUrl', 'securePath', 'mainDomain'
    ];
    for (const key of required) {
        if (!provisioned[key]) {
            throw new Error(`Provisioned settings are missing required field: ${key}`);
        }
    }

    const { searchParams, origin, hostname, pathname } = new URL(request.url);
    globalSettings = {
        nodeId: provisioned.nodeId,
        verdentUrl: provisioned.verdentUrl.replace(/\/+$/, ''),
        securePath: provisioned.securePath,
        proxyIpMode: provisioned.proxyIpMode ?? 'proxyip',
        proxyIPs: provisioned.proxyIPs?.length ? provisioned.proxyIPs : [],
        prefixes: provisioned.prefixes?.length ? provisioned.prefixes : [],
        fallback: provisioned.fallback ?? '',
        dohUrl: provisioned.dohUrl || 'https://cloudflare-dns.com/dns-query',
        mainDomain: provisioned.mainDomain,
        deployType: env.CF_PAGES === '1' ? 'pages' : 'workers',
        httpPorts: [80, 8080, 2052, 2082, 2086, 2095, 8880],
        httpsPorts: [443, 8443, 2053, 2083, 2087, 2096],
        client: decodeURIComponent(searchParams.get('app') ?? ''),
        origin: origin,
        searchParams,
        pathname: decodeURIComponent(pathname),
        hostname: hostname
    } as EmbededSettings & ReqSettings;
}

export const getGlobals = (): EmbededSettings & ReqSettings => globalSettings;

let globalSettings: EmbededSettings & ReqSettings;

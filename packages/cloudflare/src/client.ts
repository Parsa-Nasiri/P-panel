const API = "https://api.cloudflare.com/client/v4";

export interface CfResult<T> { success: boolean; errors: { code: number; message: string }[]; result: T }

export class CfClient {
  constructor(private token: string) {}

  private async req<T>(method: string, path: string, body?: unknown): Promise<CfResult<T>> {
    const res = await fetch(`${API}${path}`, {
      method,
      headers: { Authorization: `Bearer ${this.token}`, ...(body ? { "Content-Type": "application/json" } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    });
    return (await res.json()) as CfResult<T>;
  }

  async verifyToken() {
    return this.req<{ id: string; status: string }>("GET", "/user/tokens/verify");
  }

  async listAccounts() {
    return this.req<{ id: string; name: string }[]>("GET", "/accounts?per_page=50");
  }

  async listScripts(accountId: string) {
    return this.req<{ id: string; created_on: string }[]>("GET", `/accounts/${accountId}/workers/scripts`);
  }

  async workersDevSubdomain(accountId: string) {
    return this.req<{ subdomain: string } | null>("GET", `/accounts/${accountId}/workers/subdomain`);
  }

  async createKvNamespace(accountId: string, title: string) {
    return this.req<{ id: string; title: string }>("POST", `/accounts/${accountId}/storage/kv/namespaces`, { title });
  }

  async listKvNamespaces(accountId: string) {
    return this.req<{ id: string; title: string }[]>("GET", `/accounts/${accountId}/storage/kv/namespaces`);
  }

  async deleteKvNamespace(accountId: string, namespaceId: string) {
    return this.req<unknown>("DELETE", `/accounts/${accountId}/storage/kv/namespaces/${namespaceId}`);
  }

  /** Upload (deploy) a Worker bundle as an ES module with bindings. */
  async uploadWorkerScript(accountId: string, name: string, opts: {
    mainModuleContent: string;
    compatibilityDate: string;
    kvNamespaceId?: string;
    secrets?: Record<string, string>;
    bindings?: { type: string; name: string; text?: string; namespace_id?: string }[];
  }) {
    const metadata: Record<string, unknown> = {
      main_module: "worker.js",
      compatibility_date: opts.compatibilityDate,
      bindings: [
        ...(opts.kvNamespaceId ? [{ type: "kv_namespace", name: "KV", namespace_id: opts.kvNamespaceId }] : []),
        ...(opts.secrets ? Object.entries(opts.secrets).map(([k, v]) => ({ type: "secret_text", name: k, text: v })) : []),
        ...(opts.bindings ?? []),
      ],
      observability: { enabled: true },
    };
    const form = new FormData();
    form.append("metadata", new Blob([JSON.stringify(metadata)], { type: "application/json" }));
    form.append("worker.js", new Blob([opts.mainModuleContent], { type: "application/javascript+module" }), "worker.js");
    const res = await fetch(`${API}/accounts/${accountId}/workers/scripts/${name}`, {
      method: "PUT", headers: { Authorization: `Bearer ${this.token}` }, body: form,
    });
    return (await res.json()) as CfResult<{ id: string }>;
  }

  async enableWorkersDev(accountId: string, name: string, enabled = true) {
    return this.req<{ enabled: boolean }>("POST", `/accounts/${accountId}/workers/scripts/${name}/subdomain`, { enabled, previews_enabled: true });
  }

  async deleteScript(accountId: string, name: string) {
    return this.req<unknown>("DELETE", `/accounts/${accountId}/workers/scripts/${name}?force=true`);
  }
}

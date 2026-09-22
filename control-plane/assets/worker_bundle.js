// src/settings/settings.ts
Object.assign(globalThis, {
  _VL_: atob("dmxlc3M="),
  _TR_: atob("dHJvamFu"),
  _project_SM_: atob("YnBi")
});
var NODE_VERSION = "1.0.0";
function init(request, env) {
  if (!env.provisioned) {
    throw new Error("Verdent Node is missing its provisioned settings (env.provisioned). Deploy via the Control Plane provisioning flow, or provision-manual.md.");
  }
  let provisioned;
  try {
    provisioned = JSON.parse(env.provisioned);
  } catch (error) {
    throw new Error("env.provisioned is not valid JSON \u2014 refusing to start a mis-provisioned Node.");
  }
  const required = [
    "nodeId",
    "verdentUrl",
    "securePath",
    "mainDomain"
  ];
  for (const key of required) {
    if (!provisioned[key]) {
      throw new Error(`Provisioned settings are missing required field: ${key}`);
    }
  }
  const { searchParams, origin, hostname, pathname } = new URL(request.url);
  globalSettings = {
    nodeId: provisioned.nodeId,
    verdentUrl: provisioned.verdentUrl.replace(/\/+$/, ""),
    securePath: provisioned.securePath,
    proxyIpMode: provisioned.proxyIpMode ?? "proxyip",
    proxyIPs: provisioned.proxyIPs?.length ? provisioned.proxyIPs : [],
    prefixes: provisioned.prefixes?.length ? provisioned.prefixes : [],
    fallback: provisioned.fallback ?? "",
    dohUrl: provisioned.dohUrl || "https://cloudflare-dns.com/dns-query",
    mainDomain: provisioned.mainDomain,
    deployType: env.CF_PAGES === "1" ? "pages" : "workers",
    httpPorts: [80, 8080, 2052, 2082, 2086, 2095, 8880],
    httpsPorts: [443, 8443, 2053, 2083, 2087, 2096],
    client: decodeURIComponent(searchParams.get("app") ?? ""),
    origin,
    searchParams,
    pathname: decodeURIComponent(pathname),
    hostname
  };
}
var getGlobals = () => globalSettings;
var globalSettings;

// src/handlers/doh.ts
async function handleDoH(request) {
  const { dohUrl, searchParams } = getGlobals();
  const targetURL = new URL(dohUrl);
  searchParams.forEach((value, key) => {
    targetURL.searchParams.set(key, value);
  });
  const proxyRequest = new Request(targetURL.toString(), request);
  return fetch(proxyRequest);
}

// src/assets/error/index.html
var error_default = '<!DOCTYPE html>\r\n<html lang="en">\r\n\r\n<head>\r\n    <meta charset="UTF-8" />\r\n    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\r\n    <title>BPB Panel v__VERSION__</title>\r\n    <link id="favicon" rel="icon" type="image/x-icon" href="data:image/x-icon;base64,__ICON__">\r\n    <link rel="preconnect" href="https://fonts.googleapis.com">\r\n    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\r\n    <link\r\n        href="https://fonts.googleapis.com/css2?family=Ubuntu:ital,wght@0,300;0,400;0,500;0,700;1,300;1,400;1,500;1,700&display=swap"\r\n        rel="stylesheet">\r\n    <style>\r\n        :root {\r\n            --color-bg-main: linear-gradient(90deg, #000328, #00458E);\r\n            --color-text-primary: #f1f5f9;\r\n            --color-text-secondary: #aec4e2;\r\n            --shadow-header: 0.125rem 0.125rem 0.25rem #000328;\r\n            --space-sm: 0.5rem;\r\n        }\r\n\r\n        body,\r\n        html {\r\n            height: 100%;\r\n            width: 100%;\r\n            margin: 0;\r\n            display: flex;\r\n            justify-content: center;\r\n            align-items: center;\r\n            font-family: "Ubuntu", system-ui;\r\n            color: var(--color-text-secondary);\r\n            background: var(--color-bg-main);\r\n            text-align: center;\r\n            text-align: center;\r\n            -webkit-font-smoothing: antialiased;\r\n            -moz-osx-font-smoothing: grayscale;\r\n        }\r\n\r\n        h1 {\r\n            color: var(--color-text-primary);\r\n            text-shadow: var(--shadow-header);\r\n            display: flex;\r\n            justify-content: center;\r\n            align-items: stretch;\r\n            gap: var(--space-sm);\r\n        }\r\n\r\n        .header {\r\n            display: flex;\r\n            align-items: center;\r\n            justify-content: center;\r\n        }\r\n\r\n        .icon {\r\n            height: 2.5rem;\r\n        }\r\n\r\n        .panel-version {\r\n            align-self: flex-start;\r\n            font-size: large;\r\n        }\r\n    </style>\r\n</head>\r\n\r\n<body>\r\n    <div id="error-container">\r\n        <div class="header">\r\n            <img id="header-logo" src="data:image/x-icon;base64,__ICON__" alt="BPB Logo" width="48" height="48">\r\n            <h1>\r\n                BPB Panel\r\n                <span class="panel-version">\r\n                    v__VERSION__\r\n                </span>\r\n            </h1>\r\n        </div>\r\n\r\n        <div>\r\n            <h2>\u274C Something went wrong!</h2>\r\n            <p>\r\n                <b>__ERROR_MESSAGE__</b>\r\n            </p>\r\n        </div>\r\n    </div>\r\n\r\n</body>\r\n\r\n</html>';

// src/common/common.ts
function isValidUUID(uuid) {
  const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[4][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  return uuidRegex.test(uuid);
}
function safeError(error) {
  return error instanceof Error ? error.message : String(error);
}

// src/handlers/error.ts
async function renderError(error) {
  try {
    const html = error_default.replace("__ERROR_MESSAGE__", safeError(error)).replaceAll("__ICON__", "");
    return new Response(html, {
      headers: { "Content-Type": "text/html; charset=utf-8" }
    });
  } catch (err) {
    return new Response(`Error: ${safeError(error)}`, {
      headers: { "Content-Type": "text/plain; charset=utf-8" }
    });
  }
}

// src/usage/health.ts
async function renderHealth() {
  const { nodeId, mainDomain } = getGlobals();
  return Response.json({
    status: "ok",
    node: nodeId,
    mainDomain,
    version: NODE_VERSION,
    checkedAt: (/* @__PURE__ */ new Date()).toISOString()
  });
}

// src/handlers/utils.ts
async function fallback(request) {
  const { url, method, headers, body } = request;
  const { fallback: fallback2 } = getGlobals();
  if (!fallback2) return new Response("Not Found", { status: 404 /* NOT_FOUND */ });
  const newURL = new URL(url);
  newURL.hostname = fallback2;
  newURL.protocol = "https:";
  const newRequest = new Request(newURL.toString(), {
    method,
    headers,
    body,
    redirect: "manual"
  });
  return fetch(newRequest);
}

// src/protocols/trojan.ts
import { createHash } from "node:crypto";

// src/settings/users.ts
var PROXY_USERS_KEY = "proxyUsers";
var NODE_SECRET_KEY = "nodeSecret";
var CACHE_TTL_MS = 3e4;
var cachedMap = null;
var cachedAt = 0;
async function getProxyUserMap(env) {
  const now = Date.now();
  if (cachedMap && now - cachedAt < CACHE_TTL_MS) {
    return cachedMap;
  }
  try {
    const map = await env.kv.get(PROXY_USERS_KEY, { type: "json" });
    cachedMap = map ?? {};
    cachedAt = now;
    return cachedMap;
  } catch (error) {
    console.error("Failed to read proxyUsers from KV:", error);
    return cachedMap ?? {};
  }
}
async function getUserByUuid(env, uuid) {
  const map = await getProxyUserMap(env);
  const user = map[`vl:${uuid}`] ?? null;
  return user && user.status === "active" ? user : null;
}
async function getUserByTrojanHash(env, sha224Hex) {
  const map = await getProxyUserMap(env);
  const user = map[`tr:${sha224Hex}`] ?? null;
  return user && user.status === "active" ? user : null;
}
async function getNodeSecret(env) {
  try {
    return await env.kv.get(NODE_SECRET_KEY) ?? null;
  } catch (error) {
    console.error("Failed to read nodeSecret from KV:", error);
    return null;
  }
}

// src/usage/usage.ts
var FLUSH_INTERVAL_MS = 3e4;
var FLUSH_THRESHOLD_BYTES = 1024 * 1024;
var UsageTracker = class {
  constructor(configId, env, ctx) {
    this.env = env;
    this.ctx = ctx;
    this.configId = configId;
    this.connectionId = crypto.randomUUID();
  }
  env;
  ctx;
  configId;
  connectionId;
  sequenceNumber = 0;
  bytesUp = 0;
  bytesDown = 0;
  windowStartedAt = Date.now();
  closed = false;
  flushing = false;
  flushQueued = false;
  lastFlushAt = Date.now();
  trackUp(bytes) {
    if (this.closed) return;
    this.bytesUp += bytes;
    this.maybeFlush();
  }
  trackDown(bytes) {
    if (this.closed) return;
    this.bytesDown += bytes;
    this.maybeFlush();
  }
  // Called on connection close: final flush via ctx.waitUntil, covering
  // whatever accumulated since the last periodic flush (Document 3, #2).
  async close() {
    if (this.closed) return;
    this.closed = true;
    if (this.pendingBytes() === 0) return;
    await this.flush();
  }
  pendingBytes() {
    return this.bytesUp + this.bytesDown;
  }
  maybeFlush() {
    if (this.flushing || this.closed) return;
    const elapsed = Date.now() - this.lastFlushAt;
    const pending = this.pendingBytes();
    if (elapsed >= FLUSH_INTERVAL_MS || pending >= FLUSH_THRESHOLD_BYTES) {
      this.scheduleFlush();
    }
  }
  scheduleFlush() {
    if (this.flushing || this.flushQueued || this.closed) return;
    this.flushQueued = true;
    this.lastFlushAt = Date.now();
    this.ctx.waitUntil(this.flush().catch(
      (error) => console.error("Usage flush failed (queued):", error)
    ));
  }
  async flush() {
    if (this.flushing) {
      this.flushQueued = true;
      return;
    }
    this.flushing = true;
    this.flushQueued = false;
    try {
      const bytesUp = this.bytesUp;
      const bytesDown = this.bytesDown;
      const windowStartedAt = this.windowStartedAt;
      this.bytesUp = 0;
      this.bytesDown = 0;
      this.windowStartedAt = Date.now();
      this.lastFlushAt = Date.now();
      if (bytesUp === 0 && bytesDown === 0) return;
      const event = {
        configId: this.configId,
        connectionId: this.connectionId,
        sequenceNumber: ++this.sequenceNumber,
        bytesUp,
        bytesDown,
        windowStartedAt: new Date(windowStartedAt).toISOString(),
        reportedAt: (/* @__PURE__ */ new Date()).toISOString()
      };
      await postUsageEvent(this.env, event);
    } catch (error) {
      console.error("Usage flush failed:", error);
    } finally {
      this.flushing = false;
    }
  }
};
async function postUsageEvent(env, event) {
  const { nodeId, verdentUrl } = getGlobals();
  const nodeSecret = await getNodeSecret(env);
  if (!nodeSecret) {
    throw new Error("nodeSecret missing from KV \u2014 usage events cannot be signed");
  }
  const body = JSON.stringify(event);
  const timestamp = String(Date.now());
  const nonce = crypto.randomUUID().replace(/-/g, "");
  const signature = await hmacHex(nodeSecret, `${nodeId}.${timestamp}.${nonce}.${body}`);
  const res = await fetch(`${verdentUrl}/internal/nodes/${nodeId}/usage`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-verdent-node-id": nodeId,
      "x-verdent-timestamp": timestamp,
      "x-verdent-nonce": nonce,
      "x-verdent-signature": signature
    },
    body
  });
  if (!res.ok) {
    throw new Error(`Ingest endpoint returned ${res.status}`);
  }
}
async function hmacHex(secret, message) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const mac = await crypto.subtle.sign("HMAC", key, encoder.encode(message));
  return Array.from(new Uint8Array(mac), (b) => b.toString(16).padStart(2, "0")).join("");
}

// src/usage/sessions.ts
var warnedMissing = false;
async function incrSession(env, configId, deviceLimit, ctx) {
  const namespace = env.SESSION_COUNTER;
  if (!namespace) {
    if (!warnedMissing) {
      warnedMissing = true;
      console.warn("SESSION_COUNTER binding missing \u2014 device limits not enforced on this Node");
    }
    return true;
  }
  const stub = namespace.get(namespace.idFromName(configId));
  const res = await stub.fetch("https://counter/incr", {
    method: "POST",
    body: JSON.stringify({ configId, limit: deviceLimit })
  });
  if (!res.ok) {
    console.error("SessionCounter /incr failed:", res.status);
    return true;
  }
  const { allowed } = await res.json();
  return allowed;
}
async function decrSession(env, configId, ctx) {
  const namespace = env.SESSION_COUNTER;
  if (!namespace) return;
  const stub = namespace.get(namespace.idFromName(configId));
  ctx.waitUntil(
    stub.fetch("https://counter/decr", {
      method: "POST",
      body: JSON.stringify({ configId })
    }).catch((error) => console.error("SessionCounter /decr failed:", error))
  );
}

// src/protocols/common.ts
import { connect } from "cloudflare:sockets";

// src/cores/utils.ts
async function resolveDNS(domain, onlyIPv4 = false) {
  const dohBaseURL = `https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(domain)}`;
  const dohURLs = {
    ipv4: `${dohBaseURL}&type=A`,
    ipv6: `${dohBaseURL}&type=AAAA`
  };
  try {
    const ipv4 = await fetchDNSRecords(dohURLs.ipv4, 1);
    const ipv6 = onlyIPv4 ? [] : await fetchDNSRecords(dohURLs.ipv6, 28);
    return { ipv4, ipv6 };
  } catch (error) {
    throw new Error(`Error resolving DNS for ${domain}: ${safeError(error)}`);
  }
}
async function fetchDNSRecords(url, recordType) {
  try {
    const response = await fetch(url, { headers: { accept: "application/dns-json" } });
    const data = await response.json();
    if (!data.Answer) return [];
    return data.Answer.filter((record) => record.type === recordType).map((record) => record.data);
  } catch (error) {
    throw new Error(`Failed to fetch DNS records from ${url}: ${safeError(error)}`);
  }
}
function isIPv4(address) {
  const ipv4Pattern = /^(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(?:\/([0-9]|[1-2][0-9]|3[0-2]))?$/;
  return ipv4Pattern.test(address);
}
function parseHostPort(input, brackets) {
  const regex = /^(?:\[(?<ipv6>.+?)\]|(?<host>[^:]+))(:(?<port>\d+))?$/;
  const match = input.match(regex);
  if (!match || !match.groups) return { host: "", port: 0 };
  const { ipv6, host: plainHost, port: portStr } = match.groups;
  let host = ipv6 ?? plainHost ?? "";
  if (brackets && ipv6) host = `[${ipv6}]`;
  const port = portStr ? Number(portStr) : 0;
  return { host, port };
}
Array.prototype.concatIf = function(condition, concat) {
  if (!condition) return this;
  if (Array.isArray(concat)) return [...this, ...concat];
  return [...this, concat];
};
Object.prototype.omitEmpty = function() {
  if (Object.keys(this).length === 0) return void 0;
  return this;
};

// src/protocols/common.ts
var WS_READY_STATE_OPEN = 1;
var WS_READY_STATE_CLOSING = 2;
async function handleTCPOutBound(remoteSocket, addressRemote, portRemote, rawClientData, webSocket, VLResponseHeader, log, tracker) {
  async function connectAndWrite(address, port) {
    const tcpSocket = connect({
      hostname: address,
      port
    });
    remoteSocket.value = tcpSocket;
    log(`connected to ${address}:${port}`);
    const writer = tcpSocket.writable.getWriter();
    await writer.write(rawClientData);
    writer.releaseLock();
    if (rawClientData) tracker?.trackUp(rawClientData.byteLength);
    return tcpSocket;
  }
  async function retry() {
    const { proxyIpMode, proxyIPs, prefixes } = getGlobals();
    const getRandomValue = (arr) => arr[Math.floor(Math.random() * arr.length)];
    if (proxyIpMode === "proxyip") {
      log(`direct connection failed, trying to use Proxy IP for ${addressRemote}`);
      const proxyIP = getRandomValue(proxyIPs);
      if (!proxyIP) return;
      const { host, port } = parseHostPort(proxyIP, true);
      addressRemote = host || addressRemote;
      portRemote = port || portRemote;
    } else if (proxyIpMode === "prefix") {
      log(`direct connection failed, trying to generate dynamic prefix for ${addressRemote}`);
      const prefix = getRandomValue(prefixes);
      if (!prefix) return;
      const dynamicProxyIP = await getDynamicProxyIP(addressRemote, prefix);
      if (dynamicProxyIP) {
        addressRemote = dynamicProxyIP;
      } else {
        webSocket.close(1011, "Retry connection failed: Invalid Prefix");
      }
    }
    try {
      const tcpSocket = await connectAndWrite(addressRemote, portRemote);
      tcpSocket.closed.catch((error) => console.log("retry TCP socket closed error", error)).finally(() => safeCloseWebSocket(webSocket));
      remoteSocketToWS(tcpSocket, webSocket, VLResponseHeader, null, log, tracker);
    } catch (error) {
      console.error("Retry connection failed:", error);
      webSocket.close(1011, `Retry connection failed: ${safeError(error)}`);
    }
  }
  try {
    const tcpSocket = await connectAndWrite(addressRemote, portRemote);
    remoteSocketToWS(tcpSocket, webSocket, VLResponseHeader, retry, log, tracker);
  } catch (error) {
    console.error(`Connection failed: ${error}`);
    webSocket.close(1011, `Connection failed: ${safeError(error)}`);
  }
}
async function remoteSocketToWS(remoteSocket, webSocket, VLResponseHeader, retry, log, tracker) {
  let vlHeader = VLResponseHeader;
  let hasIncomingData = false;
  const writableStream = new WritableStream({
    start() {
    },
    async write(chunk, controller) {
      hasIncomingData = true;
      if (webSocket.readyState !== WS_READY_STATE_OPEN) {
        controller.error("webSocket.readyState is not open, maybe close");
      }
      tracker?.trackDown(chunk.byteLength);
      if (vlHeader) {
        webSocket.send(await new Blob([vlHeader, chunk]).arrayBuffer());
        vlHeader = null;
      } else {
        webSocket.send(chunk);
      }
    },
    close() {
      log(`remoteConnection.readable is close with hasIncomingData is ${hasIncomingData}`);
    },
    abort(reason) {
      console.error(`remoteConnection.readable abort`, reason);
      safeCloseTcpSocket(remoteSocket);
    }
  });
  try {
    await remoteSocket.readable.pipeTo(writableStream);
  } catch (error) {
    console.error("VLRemoteSocketToWS has exception.", error);
    safeCloseTcpSocket(remoteSocket);
    safeCloseWebSocket(webSocket);
  }
  if (hasIncomingData === false && retry) {
    log(`retry`);
    retry();
  }
}
function makeReadableWebSocketStream(webSocketServer, earlyDataHeader, log) {
  let readableStreamCancel = false;
  const stream = new ReadableStream({
    start(controller) {
      webSocketServer.addEventListener("message", (event) => {
        if (readableStreamCancel) return;
        controller.enqueue(event.data);
      });
      webSocketServer.addEventListener("close", () => {
        safeCloseWebSocket(webSocketServer);
        if (readableStreamCancel) return;
        controller.close();
      });
      webSocketServer.addEventListener("error", (err) => {
        log("webSocketServer has error");
        controller.error(err);
      });
      const { earlyData, error } = base64ToArrayBuffer(earlyDataHeader);
      if (error) {
        controller.error(error);
      } else if (earlyData) {
        controller.enqueue(earlyData);
      }
    },
    pull(_controller) {
    },
    cancel(reason) {
      if (readableStreamCancel) return;
      log(`ReadableStream was canceled, due to ${reason}`);
      readableStreamCancel = true;
      safeCloseWebSocket(webSocketServer);
    }
  });
  return stream;
}
function base64ToArrayBuffer(base64Str) {
  if (!base64Str) {
    return { earlyData: null, error: null };
  }
  try {
    base64Str = base64Str.replace(/-/g, "+").replace(/_/g, "/");
    const decode = atob(base64Str);
    const arryBuffer = Uint8Array.from(decode, (c) => c.charCodeAt(0));
    return { earlyData: arryBuffer.buffer, error: null };
  } catch (error) {
    return { earlyData: null, error };
  }
}
function safeCloseTcpSocket(socket) {
  if (socket) {
    try {
      socket.close();
    } catch (error) {
      console.error("Failed to close TCP socket:", error);
    }
  }
}
function safeCloseWebSocket(socket) {
  try {
    if (socket.readyState === WS_READY_STATE_OPEN || socket.readyState === WS_READY_STATE_CLOSING) {
      socket.close();
    }
  } catch (error) {
    console.error("safeCloseWebSocket error", error);
  }
}
async function getDynamicProxyIP(address, prefix) {
  let finalAddress = address;
  if (!isIPv4(address)) {
    const { ipv4 } = await resolveDNS(address, true);
    if (ipv4.length) {
      finalAddress = ipv4[0];
    } else {
      throw new Error("Unable to find IPv4 in DNS records");
    }
  }
  return convertToNAT64IPv6(finalAddress, prefix);
}
function convertToNAT64IPv6(ipv4Address, prefix) {
  const parts = ipv4Address.split(".");
  if (parts.length !== 4) {
    throw new Error("Invalid IPv4 address");
  }
  const hex = parts.map((part) => {
    const num = parseInt(part, 10);
    if (num < 0 || num > 255) {
      throw new Error("Invalid IPv4 address");
    }
    return num.toString(16).padStart(2, "0");
  });
  const match = prefix.match(/^\[([0-9A-Fa-f:]+)\]$/);
  if (match) {
    return `[${match[1]}${hex[0]}${hex[1]}:${hex[2]}${hex[3]}]`;
  }
}

// src/protocols/trojan.ts
async function TrOverWSHandler(request, env, ctx) {
  const webSocketPair = new WebSocketPair();
  const [client, webSocket] = Object.values(webSocketPair);
  webSocket.accept();
  webSocket.binaryType = "arraybuffer";
  let address = "";
  let portWithRandomLog = "";
  const log = (info, event) => {
    console.log(`[${address}:${portWithRandomLog}] ${info}`, event || "");
  };
  const earlyDataHeader = request.headers.get("sec-websocket-protocol") || "";
  const readableWebSocketStream = makeReadableWebSocketStream(webSocket, earlyDataHeader, log);
  let remoteSocketWapper = { value: null };
  let udpStreamWrite = null;
  let tracker = null;
  let userConfigId = null;
  let admitted = false;
  const finalize = async () => {
    if (admitted && userConfigId) await decrSession(env, userConfigId, ctx);
    if (tracker) await tracker.close();
  };
  const writableStream = new WritableStream({
    async write(chunk, _controller) {
      if (udpStreamWrite) {
        return udpStreamWrite(chunk);
      }
      if (remoteSocketWapper.value) {
        const writer = remoteSocketWapper.value.writable.getWriter();
        await writer.write(chunk);
        writer.releaseLock();
        if (tracker) tracker.trackUp(chunk.byteLength);
        return;
      }
      const parsed = await parseTrHeader(chunk, env, ctx, log);
      address = parsed.addressRemote ?? "";
      portWithRandomLog = `${parsed.portRemote ?? 443}--${Math.random()} tcp`;
      if (parsed.hasError || !parsed.configId) {
        throw new Error(parsed.message);
      }
      admitted = true;
      userConfigId = parsed.configId;
      tracker = new UsageTracker(parsed.configId, env, ctx);
      handleTCPOutBound(
        remoteSocketWapper,
        parsed.addressRemote ?? "",
        parsed.portRemote ?? 443,
        parsed.rawClientData,
        webSocket,
        null,
        log,
        tracker
      );
    },
    close() {
      safeCloseTcpSocket(remoteSocketWapper.value);
      ctx.waitUntil(finalize());
    },
    abort(reason) {
      log(`readableWebSocketStream is aborted`, JSON.stringify(reason));
      ctx.waitUntil(finalize());
    }
  });
  readableWebSocketStream.pipeTo(writableStream).catch((error) => {
    log("readableWebSocketStream pipeTo error", error);
    safeCloseTcpSocket(remoteSocketWapper.value);
    ctx.waitUntil(finalize());
  });
  return new Response(null, {
    status: 101,
    webSocket: client
  });
}
async function parseTrHeader(buffer, env, ctx, log) {
  if (buffer.byteLength < 56) {
    return { hasError: true, message: "invalid data" };
  }
  let crLfIndex = 56;
  const cr = new Uint8Array(buffer.slice(crLfIndex, crLfIndex + 1))[0];
  const lf = new Uint8Array(buffer.slice(crLfIndex + 1, crLfIndex + 2))[0];
  if (cr !== 13 || lf !== 10) {
    return { hasError: true, message: "invalid header format (missing CR LF)" };
  }
  const password = new TextDecoder().decode(buffer.slice(0, crLfIndex));
  const sha224Hex = createHash("sha224").update(password).digest("hex");
  const user = await getUserByTrojanHash(env, sha224Hex);
  if (!user) {
    log("invalid password");
    return { hasError: true, message: "invalid password" };
  }
  const deviceLimit = user.deviceLimit ?? 1;
  const admitted = await incrSession(env, user.configId, deviceLimit, ctx);
  if (!admitted) {
    log("device limit reached");
    return { hasError: true, message: "device limit reached" };
  }
  const socks5DataBuffer = buffer.slice(crLfIndex + 2);
  if (socks5DataBuffer.byteLength < 6) {
    return { hasError: true, message: "invalid SOCKS5 request data" };
  }
  const view = new DataView(socks5DataBuffer);
  const cmd = view.getUint8(0);
  if (cmd !== 1) {
    return { hasError: true, message: "unsupported command, only TCP (CONNECT) is allowed" };
  }
  const atype = view.getUint8(1);
  let addressLength = 0;
  let addressIndex = 2;
  let address = "";
  switch (atype) {
    case 1:
      addressLength = 4;
      address = new Uint8Array(socks5DataBuffer.slice(addressIndex, addressIndex + addressLength)).join(".");
      break;
    case 3:
      addressLength = new Uint8Array(socks5DataBuffer.slice(addressIndex, addressIndex + 1))[0];
      addressIndex += 1;
      address = new TextDecoder().decode(socks5DataBuffer.slice(addressIndex, addressIndex + addressLength));
      break;
    case 4: {
      addressLength = 16;
      const dataView = new DataView(socks5DataBuffer.slice(addressIndex, addressIndex + addressLength));
      const ipv6 = [];
      for (let i = 0; i < 8; i++) {
        ipv6.push(dataView.getUint16(i * 2).toString(16));
      }
      address = ipv6.join(":");
      break;
    }
    default:
      return { hasError: true, message: `invalid addressType is ${atype}` };
  }
  if (!address) {
    return { hasError: true, message: `address is empty, addressType is ${atype}` };
  }
  const portIndex = addressIndex + addressLength;
  const portBuffer = socks5DataBuffer.slice(portIndex, portIndex + 2);
  const portRemote = new DataView(portBuffer).getUint16(0);
  return {
    hasError: false,
    addressRemote: address,
    portRemote,
    rawClientData: socks5DataBuffer.slice(portIndex + 4),
    configId: user.configId
  };
}

// src/protocols/vless.ts
async function VlOverWSHandler(request, env, ctx) {
  const webSocketPair = new WebSocketPair();
  const [client, webSocket] = Object.values(webSocketPair);
  webSocket.accept();
  webSocket.binaryType = "arraybuffer";
  let address = "";
  let portWithRandomLog = "";
  const log = (info, event) => {
    console.log(`[${address}:${portWithRandomLog}] ${info}`, event || "");
  };
  const earlyDataHeader = request.headers.get("sec-websocket-protocol") || "";
  const readableWebSocketStream = makeReadableWebSocketStream(webSocket, earlyDataHeader, log);
  let remoteSocketWapper = { value: null };
  let udpStreamWrite = null;
  let isDns = false;
  let tracker = null;
  let userConfigId = null;
  let admitted = false;
  const finalize = async () => {
    if (admitted && userConfigId) await decrSession(env, userConfigId, ctx);
    if (tracker) await tracker.close();
  };
  const writableStream = new WritableStream({
    async write(chunk) {
      if (isDns && udpStreamWrite) {
        return udpStreamWrite(chunk);
      }
      if (remoteSocketWapper.value) {
        const writer = remoteSocketWapper.value.writable.getWriter();
        await writer.write(chunk);
        writer.releaseLock();
        if (tracker) tracker.trackUp(chunk.byteLength);
        return;
      }
      const parsed = await parseVlHeader(chunk, env, ctx, log);
      address = parsed.addressRemote ?? "";
      portWithRandomLog = `${parsed.portRemote ?? 443}--${Math.random()} ${parsed.isUDP ? "udp " : "tcp "} `;
      if (parsed.hasError || !parsed.configId) {
        throw new Error(parsed.message);
      }
      admitted = true;
      userConfigId = parsed.configId;
      tracker = new UsageTracker(parsed.configId, env, ctx);
      const VLResponseHeader = new Uint8Array([parsed.VLVersion[0], 0]);
      const rawClientData = chunk.slice(parsed.rawDataIndex);
      if (parsed.isUDP) {
        if (parsed.portRemote === 53) {
          isDns = true;
          const { write } = await handleUDPOutBound(webSocket, VLResponseHeader, log);
          udpStreamWrite = write;
          await udpStreamWrite(rawClientData);
          return;
        } else {
          throw new Error("UDP proxy only enable for DNS which is port 53");
        }
      }
      handleTCPOutBound(
        remoteSocketWapper,
        parsed.addressRemote ?? "",
        parsed.portRemote ?? 443,
        rawClientData,
        webSocket,
        VLResponseHeader,
        log,
        tracker
      );
    },
    close() {
      safeCloseTcpSocket(remoteSocketWapper.value);
      ctx.waitUntil(finalize());
    },
    abort(reason) {
      log(`readableWebSocketStream is abort`, JSON.stringify(reason));
      ctx.waitUntil(finalize());
    }
  });
  readableWebSocketStream.pipeTo(writableStream).catch((error) => {
    log("readableWebSocketStream pipeTo error", error);
    safeCloseTcpSocket(remoteSocketWapper.value);
    ctx.waitUntil(finalize());
  });
  return new Response(null, {
    status: 101,
    webSocket: client
  });
}
async function parseVlHeader(VLBuffer, env, ctx, log) {
  if (VLBuffer.byteLength < 24) {
    return { hasError: true, message: "invalid data" };
  }
  const VLVersion = new Uint8Array(VLBuffer.slice(0, 1));
  const slicedBuffer = new Uint8Array(VLBuffer.slice(1, 17));
  const slicedBufferString = stringify(slicedBuffer);
  const user = await getUserByUuid(env, slicedBufferString);
  if (!user) {
    log("invalid user");
    return { hasError: true, message: "invalid user" };
  }
  const deviceLimit = user.deviceLimit ?? 1;
  const admitted = await incrSession(env, user.configId, deviceLimit, ctx);
  if (!admitted) {
    log("device limit reached");
    return { hasError: true, message: "device limit reached" };
  }
  const optLength = new Uint8Array(VLBuffer.slice(17, 18))[0];
  const command = new Uint8Array(VLBuffer.slice(18 + optLength, 18 + optLength + 1))[0];
  let isUDP = false;
  if (command === 1) {
  } else if (command === 2) {
    isUDP = true;
  } else {
    return {
      hasError: true,
      message: `command ${command} is not supported, command 01-tcp,02-udp,03-mux`
    };
  }
  const portIndex = 18 + optLength + 1;
  const portBuffer = VLBuffer.slice(portIndex, portIndex + 2);
  const portRemote = new DataView(portBuffer).getUint16(0);
  let addressIndex = portIndex + 2;
  const addressBuffer = new Uint8Array(VLBuffer.slice(addressIndex, addressIndex + 1));
  const addressType = addressBuffer[0];
  let addressLength = 0;
  let addressValueIndex = addressIndex + 1;
  let addressValue = "";
  switch (addressType) {
    case 1:
      addressLength = 4;
      addressValue = new Uint8Array(VLBuffer.slice(addressValueIndex, addressValueIndex + addressLength)).join(".");
      break;
    case 2:
      addressLength = new Uint8Array(VLBuffer.slice(addressValueIndex, addressValueIndex + 1))[0];
      addressValueIndex += 1;
      addressValue = new TextDecoder().decode(VLBuffer.slice(addressValueIndex, addressValueIndex + addressLength));
      break;
    case 3: {
      addressLength = 16;
      const dataView = new DataView(VLBuffer.slice(addressValueIndex, addressValueIndex + addressLength));
      const ipv6 = [];
      for (let i = 0; i < 8; i++) {
        ipv6.push(dataView.getUint16(i * 2).toString(16));
      }
      addressValue = ipv6.join(":");
      break;
    }
    default:
      return {
        hasError: true,
        message: `invalid addressType is ${addressType}`
      };
  }
  if (!addressValue) {
    return {
      hasError: true,
      message: `addressValue is empty, addressType is ${addressType}`
    };
  }
  return {
    hasError: false,
    addressRemote: addressValue,
    portRemote,
    rawDataIndex: addressValueIndex + addressLength,
    VLVersion,
    isUDP,
    configId: user.configId
  };
}
function unsafeStringify(arr, offset = 0) {
  const byteToHex = [];
  for (let i = 0; i < 256; ++i) {
    byteToHex.push((i + 256).toString(16).slice(1));
  }
  return (byteToHex[arr[offset + 0]] + byteToHex[arr[offset + 1]] + byteToHex[arr[offset + 2]] + byteToHex[arr[offset + 3]] + "-" + byteToHex[arr[offset + 4]] + byteToHex[arr[offset + 5]] + "-" + byteToHex[arr[offset + 6]] + byteToHex[arr[offset + 7]] + "-" + byteToHex[arr[offset + 8]] + byteToHex[arr[offset + 9]] + "-" + byteToHex[arr[offset + 10]] + byteToHex[arr[offset + 11]] + byteToHex[arr[offset + 12]] + byteToHex[arr[offset + 13]] + byteToHex[arr[offset + 14]] + byteToHex[arr[offset + 15]]).toLowerCase();
}
function stringify(arr, offset = 0) {
  const uuid = unsafeStringify(arr, offset);
  if (!isValidUUID(uuid)) {
    throw TypeError("Stringified UUID is invalid");
  }
  return uuid;
}
async function handleUDPOutBound(webSocket, VLResponseHeader, log) {
  let isVLHeaderSent = false;
  const transformStream = new TransformStream({
    start(_controller) {
    },
    transform(chunk, controller) {
      for (let index = 0; index < chunk.byteLength; ) {
        const lengthBuffer = chunk.slice(index, index + 2);
        const udpPakcetLength = new DataView(lengthBuffer).getUint16(0);
        const udpData = new Uint8Array(chunk.slice(index + 2, index + 2 + udpPakcetLength));
        index = index + 2 + udpPakcetLength;
        controller.enqueue(udpData);
      }
    },
    flush(_controller) {
    }
  });
  transformStream.readable.pipeTo(
    new WritableStream({
      async write(chunk) {
        const resp = await fetch("https://cloudflare-dns.com/dns-query", {
          method: "POST",
          headers: {
            "content-type": "application/dns-message"
          },
          body: chunk
        });
        const dnsQueryResult = await resp.arrayBuffer();
        const udpSize = dnsQueryResult.byteLength;
        const udpSizeBuffer = new Uint8Array([udpSize >> 8 & 255, udpSize & 255]);
        if (webSocket.readyState === WS_READY_STATE_OPEN) {
          log(`doh success and dns message length is ${udpSize}`);
          if (isVLHeaderSent) {
            webSocket.send(await new Blob([udpSizeBuffer, dnsQueryResult]).arrayBuffer());
          } else {
            webSocket.send(await new Blob([VLResponseHeader, udpSizeBuffer, dnsQueryResult]).arrayBuffer());
            isVLHeaderSent = true;
          }
        }
      }
    })
  ).catch((error) => {
    log("dns udp has error" + error);
  });
  const writer = transformStream.writable.getWriter();
  return {
    async write(chunk) {
      await writer.write(chunk);
    }
  };
}

// src/handlers/websocket.ts
async function handleWebsocket(request, env, ctx) {
  const { pathname } = getGlobals();
  const protocol = pathname.split("/")[1];
  try {
    switch (protocol) {
      case "vl":
        return VlOverWSHandler(request, env, ctx);
      case "tr":
        return TrOverWSHandler(request, env, ctx);
      default:
        return fallback(request);
    }
  } catch (error) {
    return new Response("Bad Request", { status: 400 /* BAD_REQUEST */ });
  }
}

// src/usage/session-counter.ts
var SessionCounter = class {
  // In-memory state: single-object, single-threaded per Configuration name
  // (idFromName(configId)) — this IS the strong consistency primitive.
  sessions = /* @__PURE__ */ new Map();
  async fetch(request) {
    const url = new URL(request.url);
    try {
      if (request.method === "POST" && url.pathname === "/incr") {
        const { configId, limit } = await request.json();
        const current = this.sessions.get(configId) ?? 0;
        const allowed = current < limit;
        if (allowed) {
          this.sessions.set(configId, current + 1);
        }
        return Response.json({ allowed, count: allowed ? current + 1 : current });
      }
      if (request.method === "POST" && url.pathname === "/decr") {
        const { configId } = await request.json();
        const current = this.sessions.get(configId) ?? 0;
        const next = Math.max(0, current - 1);
        if (next === 0) {
          this.sessions.delete(configId);
        } else {
          this.sessions.set(configId, next);
        }
        return Response.json({ count: next });
      }
      if (request.method === "GET" && url.pathname === "/count") {
        const configId = url.searchParams.get("configId") ?? "";
        return Response.json({ count: this.sessions.get(configId) ?? 0 });
      }
      return Response.json({ error: "not found" }, { status: 404 });
    } catch (error) {
      return Response.json({ error: String(error) }, { status: 400 });
    }
  }
};

// src/worker.ts
var worker_default = {
  async fetch(request, env, ctx) {
    try {
      init(request, env);
      if (request.headers.get("Upgrade") === "websocket") return handleWebsocket(request, env, ctx);
      const { securePath, pathname } = getGlobals();
      const path = pathname.split("/").splice(0, 3).join("/");
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
export {
  SessionCounter,
  worker_default as default
};

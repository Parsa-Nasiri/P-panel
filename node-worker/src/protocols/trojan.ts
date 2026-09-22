import { createHash } from 'node:crypto';
import { getGlobals } from '@settings';
import { getUserByTrojanHash } from '@settings/users';
import { UsageTracker } from '@usage/usage';
import { incrSession, decrSession } from '@usage/sessions';
import { handleTCPOutBound, makeReadableWebSocketStream, safeCloseTcpSocket } from '@protocols/common';

// Verdent fork (Document 1, "BPB Fork Scope" #1, #2): the Trojan check is no
// longer an equality test against one global password — it is a map lookup
// against this Node's KV `proxyUsers` map keyed by SHA-224(password)-hex,
// written by the Control Plane. On no match, the socket is closed.

export async function TrOverWSHandler(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const webSocketPair = new WebSocketPair();
    const [client, webSocket] = Object.values(webSocketPair);
    webSocket.accept();
    webSocket.binaryType = 'arraybuffer';

    let address = '';
    let portWithRandomLog = '';

    const log = (info: string, event?: string) => {
        console.log(`[${address}:${portWithRandomLog}] ${info}`, event || '');
    };

    const earlyDataHeader = request.headers.get('sec-websocket-protocol') || '';
    const readableWebSocketStream = makeReadableWebSocketStream(webSocket, earlyDataHeader, log);

    let remoteSocketWapper: { value: any } = { value: null };
    let udpStreamWrite: any = null;

    let tracker: UsageTracker | null = null;
    let userConfigId: string | null = null;
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

            address = parsed.addressRemote ?? '';
            portWithRandomLog = `${parsed.portRemote ?? 443}--${Math.random()} tcp`;

            if (parsed.hasError || !parsed.configId) {
                throw new Error(parsed.message);
            }

            // Verdent fork: resolution + admission succeeded — open this
            // connection's ledger slice.
            admitted = true;
            userConfigId = parsed.configId;
            tracker = new UsageTracker(parsed.configId, env, ctx);

            handleTCPOutBound(
                remoteSocketWapper,
                parsed.addressRemote ?? '',
                parsed.portRemote ?? 443,
                parsed.rawClientData!,
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

    readableWebSocketStream
        .pipeTo(writableStream)
        .catch(error => {
            log('readableWebSocketStream pipeTo error', error);
            safeCloseTcpSocket(remoteSocketWapper.value);
            ctx.waitUntil(finalize());
        });

    return new Response(null, {
        status: 101,
        webSocket: client,
    });
}

interface TrParsed {
    hasError: boolean;
    message?: string;
    addressRemote?: string;
    portRemote?: number;
    rawClientData?: ArrayBuffer;
    configId?: string;
}

async function parseTrHeader(
    buffer: ArrayBuffer,
    env: Env,
    ctx: ExecutionContext,
    log: Function
): Promise<TrParsed> {
    if (buffer.byteLength < 56) {
        return { hasError: true, message: 'invalid data' };
    }

    let crLfIndex = 56;
    const cr = new Uint8Array(buffer.slice(crLfIndex, crLfIndex + 1))[0];
    const lf = new Uint8Array(buffer.slice(crLfIndex + 1, crLfIndex + 2))[0];

    if (cr !== 0x0d || lf !== 0x0a) {
        return { hasError: true, message: 'invalid header format (missing CR LF)' };
    }

    const password = new TextDecoder().decode(buffer.slice(0, crLfIndex));
    const sha224Hex = createHash('sha224').update(password).digest('hex');

    const user = await getUserByTrojanHash(env, sha224Hex);

    if (!user) {
        log('invalid password');
        return { hasError: true, message: 'invalid password' };
    }

    const deviceLimit = user.deviceLimit ?? 1;
    const admitted = await incrSession(env, user.configId, deviceLimit, ctx);

    if (!admitted) {
        log('device limit reached');
        return { hasError: true, message: 'device limit reached' };
    }

    const socks5DataBuffer = buffer.slice(crLfIndex + 2);
    if (socks5DataBuffer.byteLength < 6) {
        return { hasError: true, message: 'invalid SOCKS5 request data' };
    }

    const view = new DataView(socks5DataBuffer);
    const cmd = view.getUint8(0);
    if (cmd !== 1) {
        return { hasError: true, message: 'unsupported command, only TCP (CONNECT) is allowed' };
    }

    const atype = view.getUint8(1);
    let addressLength = 0;
    let addressIndex = 2;
    let address = '';

    switch (atype) {
        case 1:
            addressLength = 4;
            address = new Uint8Array(socks5DataBuffer.slice(addressIndex, addressIndex + addressLength)).join('.');
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

            address = ipv6.join(':');
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
        configId: user.configId,
    };
}

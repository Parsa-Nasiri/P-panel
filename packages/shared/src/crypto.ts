import { createCipheriv, createDecipheriv, createHmac, randomBytes, scryptSync, timingSafeEqual, createHash } from "node:crypto";

const KEY_INFO = "proxy-panel-v1";

let cachedKey: Buffer | null = null;
function masterKey(appSecret: string): Buffer {
  if (!cachedKey) cachedKey = scryptSync(appSecret, KEY_INFO, 32);
  return cachedKey;
}

/** AES-256-GCM envelope encryption for CF tokens / node secrets. */
export function encryptSecret(plain: string, appSecret: string) {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", masterKey(appSecret), iv);
  const enc = Buffer.concat([cipher.update(plain, "utf8"), cipher.final()]);
  return { enc: enc.toString("base64"), iv: iv.toString("base64"), tag: cipher.getAuthTag().toString("base64") };
}

export function decryptSecret(box: { enc: string; iv: string; tag: string }, appSecret: string): string {
  const decipher = createDecipheriv("aes-256-gcm", masterKey(appSecret), Buffer.from(box.iv, "base64"));
  decipher.setAuthTag(Buffer.from(box.tag, "base64"));
  return Buffer.concat([decipher.update(Buffer.from(box.enc, "base64")), decipher.final()]).toString("utf8");
}

export function sha256(v: string): string {
  return createHash("sha256").update(v).digest("hex");
}

export function randomToken(bytes = 32): string {
  return randomBytes(bytes).toString("base64url");
}

/** Password hashing: scrypt with per-password salt (no native deps). */
export function hashPassword(password: string): string {
  const salt = randomBytes(16);
  const hash = scryptSync(password, salt, 64, { N: 16384, r: 8, p: 1 });
  return `scrypt$${salt.toString("base64")}$${hash.toString("base64")}`;
}

export function verifyPassword(password: string, stored: string): boolean {
  const [scheme, saltB64, hashB64] = stored.split("$");
  if (scheme !== "scrypt") return false;
  const hash = scryptSync(password, Buffer.from(saltB64, "base64"), 64, { N: 16384, r: 8, p: 1 });
  return timingSafeEqual(hash, Buffer.from(hashB64, "base64"));
}

/** Node uplink request signing: HMAC over "method:path:timestamp:bodySha256". */
export function nodeSignature(secret: string, method: string, path: string, ts: string, bodyRaw: string): string {
  const bodyHash = createHash("sha256").update(bodyRaw).digest("hex");
  return createHmac("sha256", secret).update(`${method.toUpperCase()}:${path}:${ts}:${bodyHash}`).digest("hex");
}

export function verifyNodeSignature(secret: string, method: string, path: string, ts: string, bodyRaw: string, signature: string, maxSkewSec = 90): boolean {
  const now = Math.floor(Date.now() / 1000);
  if (Math.abs(now - Number(ts)) > maxSkewSec) return false;
  const expected = nodeSignature(secret, method, path, ts, bodyRaw);
  const a = Buffer.from(expected, "hex");
  const b = Buffer.from(signature, "hex");
  return a.length === b.length && timingSafeEqual(a, b);
}

export function hmacSign(payload: string, secret: string): string {
  return createHmac("sha256", secret).update(payload).digest("hex");
}

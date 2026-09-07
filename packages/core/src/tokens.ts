import { createHash } from "node:crypto";
import { randomToken } from "@proxy/shared";

const ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789";

/** Immutable public code: P-ejrnfk-123 (10 chars, 5-3 split). */
export function newSubCode(): string {
  const chars: string[] = [];
  for (let i = 0; i < 10; i++) chars.push(ALPHABET[Math.floor(Math.random() * ALPHABET.length)]);
  const s = chars.join("");
  return `P-${s.slice(0, 5)}-${s.slice(5)}`;
}

/** 256-bit subscription token; only its SHA-256 hash is persisted. */
export function newSubToken(): { token: string; tokenHash: string } {
  const token = randomToken(32);
  return { token, tokenHash: createHash("sha256").update(token).digest("hex") };
}

export function hashToken(token: string): string {
  return createHash("sha256").update(token).digest("hex");
}

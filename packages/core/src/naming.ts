/**
 * Config naming rule (shared by panel + bot):
 * customer name <= 20 chars -> display name `{name}_{5digits}`, unique per user.
 */
export const MAX_NAME_LEN = 20;

export function sanitizeName(raw: string): { ok: true; value: string } | { ok: false; reason: "empty" | "too_long" | "invalid" } {
  const value = raw.normalize("NFC").replace(/[\u200c\u200f\u200e]/g, "").replace(/\s+/g, " ").trim();
  if (!value) return { ok: false, reason: "empty" };
  if (Array.from(value).length > MAX_NAME_LEN) return { ok: false, reason: "too_long" };
  // unicode letters (incl. Persian), digits, space, -, _
  if (!/^[\p{L}\p{N}][\p{L}\p{N} _-]*$/u.test(value)) return { ok: false, reason: "invalid" };
  return { ok: true, value };
}

function rand5(): string {
  return String(Math.floor(10000 + Math.random() * 90000));
}

/** Builds display name, regenerating on collision (max 8 attempts). */
export async function buildDisplayName(name: string, isTaken: (candidate: string) => Promise<boolean>): Promise<string> {
  for (let i = 0; i < 8; i++) {
    const candidate = `${name}_${rand5()}`;
    if (!(await isTaken(candidate))) return candidate;
  }
  return `${name}_${Date.now() % 100000}`;
}

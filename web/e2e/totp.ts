import { createHmac } from 'node:crypto';

/**
 * Code TOTP RFC 6238 (SHA-1, 6 chiffres, 30 s) calculé par le navigateur de test, comme
 * l'application d'authentification d'un membre du comité (secret de test de `seed.py`).
 */
function base32(secret: string): Buffer {
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const bits = [...secret.replace(/=+$/, '').toUpperCase()]
    .map((char) => alphabet.indexOf(char).toString(2).padStart(5, '0'))
    .join('');
  const bytes: number[] = [];
  for (let index = 0; index + 8 <= bits.length; index += 8) {
    bytes.push(parseInt(bits.slice(index, index + 8), 2));
  }
  return Buffer.from(bytes);
}

export function totpCode(secret: string, at = Date.now()): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 30_000)));
  const digest = createHmac('sha1', base32(secret)).update(counter).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  return String((digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).padStart(6, '0');
}

/** Dernière fenêtre de 30 s dont un code a servi, par compte (un code ne sert qu'une fois). */
const usedWindows = new Map<string, number>();

/**
 * Code encore valable quelques secondes : attend la fenêtre suivante s'il expire bientôt, ou
 * si ce compte a déjà employé le code de la fenêtre en cours (allauth refuse le rejeu d'un
 * code, à juste titre ; tous les membres de test partagent le même secret).
 */
export async function freshTotpCode(secret: string, account = ''): Promise<string> {
  const now = Date.now();
  const left = 30_000 - (now % 30_000);
  if (left < 5_000 || usedWindows.get(account) === Math.floor(now / 30_000)) {
    await new Promise((resolve) => setTimeout(resolve, left + 250));
  }
  usedWindows.set(account, Math.floor(Date.now() / 30_000));
  return totpCode(secret);
}

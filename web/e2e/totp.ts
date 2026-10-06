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

/** Code encore valable quelques secondes : attend la fenêtre suivante s'il expire bientôt. */
export async function freshTotpCode(secret: string): Promise<string> {
  const left = 30_000 - (Date.now() % 30_000);
  if (left < 5_000) {
    await new Promise((resolve) => setTimeout(resolve, left + 250));
  }
  return totpCode(secret);
}

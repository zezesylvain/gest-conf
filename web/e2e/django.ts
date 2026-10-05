import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';

/**
 * Accès de l'E2E au backend, comme un opérateur : `manage.py` (commandes et `shell`) sur la
 * base SQLite de la série. Sert à préparer les données, à suivre un lien reçu par e-mail
 * (la clé est recalculée, l'e-mail part en console) et à simuler la clôture de l'appel.
 */
export const E2E_DATABASE_URL = 'sqlite:////tmp/gestconf-e2e.sqlite3';
export const PYTHON = process.env['GESTCONF_E2E_PYTHON'] ?? 'python';
export const BACKEND_DIR = resolve(__dirname, '../../backend');
export const BACKEND_ENV = {
  DATABASE_URL: E2E_DATABASE_URL,
  DJANGO_SETTINGS_MODULE: 'config.settings.dev',
};

function manage(args: string[], input?: string): string {
  return execFileSync(PYTHON, ['manage.py', ...args], {
    cwd: BACKEND_DIR,
    env: { ...process.env, ...BACKEND_ENV },
    input,
    encoding: 'utf8',
  }).trim();
}

/** Code Python exécuté par `manage.py shell` ; renvoie ce qu'il imprime. */
export function python(code: string): string {
  return manage(['shell', '-v', '0'], code);
}

export function command(...args: string[]): string {
  return manage([...args, '-v', '0']);
}

/** Valeur Python sûre (chaîne échappée en JSON, compatible avec la syntaxe Python). */
export function literal(value: string): string {
  return JSON.stringify(value);
}

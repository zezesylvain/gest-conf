import { InvitableRole, Role } from '@gestconf/shared';

/**
 * Qui peut attribuer ou retirer quel rôle (plan L1 §5.5, D7), **recopié pour l'interface
 * seulement** (masquer les boutons inutiles) : le serveur applique sa propre table
 * (`apps/accounts/roles.py`, GRANTORS) et refuse le reste (règle n° 2).
 */
const GRANTORS: Partial<Record<Role, InvitableRole[]>> = {
  ADMIN: ['ADMIN', 'CHAIR', 'SC_CHAIR', 'OC_MEMBER', 'SC_MEMBER'],
  CHAIR: ['SC_CHAIR', 'OC_MEMBER', 'SC_MEMBER'],
  SC_CHAIR: ['SC_MEMBER'],
};

export function manageableRoles(roles: readonly string[]): InvitableRole[] {
  const result = new Set<InvitableRole>();
  for (const role of roles) {
    for (const target of GRANTORS[role as Role] ?? []) {
      result.add(target);
    }
  }
  return [...result];
}

export const OC_FUNCTIONS = [
  'finance',
  'program',
  'logistics',
  'communication',
  'external_relations',
  'volunteers',
  'secretariat',
] as const;

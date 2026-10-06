import { InvitableRole, OcFunction, Role } from '@gestconf/shared';

/**
 * Qui peut attribuer ou retirer quel rôle (plan L1 §5.5, D7 ; plan L7, K1 et K18),
 * **recopié pour l'interface seulement** (masquer les boutons inutiles) : le serveur applique
 * sa propre table (`apps/accounts/roles.py`, GRANTORS et FUNCTION_GRANTORS) et refuse le
 * reste (règle n° 2). Intervenants et présidents de séance s'invitent depuis le programme.
 */
const GRANTORS: Partial<Record<Role, InvitableRole[]>> = {
  ADMIN: ['ADMIN', 'CHAIR', 'SC_CHAIR', 'OC_MEMBER', 'SC_MEMBER', 'VOLUNTEER', 'SIGNATORY'],
  CHAIR: ['SC_CHAIR', 'OC_MEMBER', 'SC_MEMBER', 'VOLUNTEER', 'SIGNATORY'],
  SC_CHAIR: ['SC_MEMBER'],
};

/** Par fonction au CO : le CO « bénévoles » recrute les bénévoles (K1, plan L7). */
const FUNCTION_GRANTORS: Partial<Record<OcFunction, InvitableRole[]>> = {
  volunteers: ['VOLUNTEER'],
};

export interface RoleAssignment {
  readonly role: string;
  readonly oc_function?: string;
}

export function manageableRoles(assignments: readonly RoleAssignment[]): InvitableRole[] {
  const result = new Set<InvitableRole>();
  for (const { role, oc_function } of assignments) {
    for (const target of GRANTORS[role as Role] ?? []) {
      result.add(target);
    }
    if (role === 'OC_MEMBER' && oc_function) {
      for (const target of FUNCTION_GRANTORS[oc_function as OcFunction] ?? []) {
        result.add(target);
      }
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

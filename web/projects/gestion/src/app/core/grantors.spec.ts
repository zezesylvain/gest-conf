import { manageableRoles } from './grantors';

describe('manageableRoles', () => {
  it('suit la table du serveur pour les rôles de pilotage (plan L7, K1 et K18)', () => {
    expect(manageableRoles([{ role: 'CHAIR', oc_function: '' }])).toEqual([
      'SC_CHAIR',
      'OC_MEMBER',
      'SC_MEMBER',
      'VOLUNTEER',
      'SIGNATORY',
    ]);
    expect(manageableRoles([{ role: 'SC_CHAIR', oc_function: '' }])).toEqual(['SC_MEMBER']);
  });

  it('donne les bénévoles au seul CO « bénévoles »', () => {
    expect(manageableRoles([{ role: 'OC_MEMBER', oc_function: 'volunteers' }])).toEqual([
      'VOLUNTEER',
    ]);
    expect(manageableRoles([{ role: 'OC_MEMBER', oc_function: 'finance' }])).toEqual([]);
    expect(manageableRoles([{ role: 'VOLUNTEER', oc_function: '' }])).toEqual([]);
  });

  it("fait l'union des rôles cumulés, sans doublon", () => {
    expect(
      manageableRoles([
        { role: 'SC_CHAIR', oc_function: '' },
        { role: 'OC_MEMBER', oc_function: 'volunteers' },
        { role: 'OC_MEMBER', oc_function: 'secretariat' },
      ]),
    ).toEqual(['SC_MEMBER', 'VOLUNTEER']);
  });
});

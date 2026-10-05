import { TestBed } from '@angular/core/testing';
import { useTestLanguage } from '@gestconf/shared/testing';

import { provideGestionTesting } from '../../../testing/gestion-testing';
import { EditionApi } from '../../core/edition-api';
import { InvitationsPage, parseEmails } from './invitations-page';

describe('InvitationsPage', () => {
  let api: Record<string, ReturnType<typeof vi.fn>>;

  beforeEach(async () => {
    api = {
      invitations: vi.fn().mockResolvedValue({ count: 0, results: [] }),
      invite: vi.fn(),
    };
    TestBed.configureTestingModule({
      imports: [InvitationsPage],
      providers: [...provideGestionTesting(), { provide: EditionApi, useValue: api }],
    });
    await useTestLanguage('fr');
  });

  it('découpe et dédoublonne les adresses', () => {
    expect(parseEmails('A@x.org, b@x.org;\n a@x.org  c@x.org')).toEqual([
      'a@x.org',
      'b@x.org',
      'c@x.org',
    ]);
  });

  it('rôles proposés selon la table d’attribution (CHAIR : pas ADMIN ni CHAIR)', async () => {
    const fixture = TestBed.createComponent(InvitationsPage);
    fixture.componentRef.setInput('editionId', '3');
    await fixture.whenStable();
    const roles = (fixture.componentInstance as unknown as { roles: () => string[] }).roles();
    expect(roles).toEqual(['SC_CHAIR', 'OC_MEMBER', 'SC_MEMBER']);
  });

  it('adresse invalide : aucun envoi, message sur le champ', async () => {
    const fixture = TestBed.createComponent(InvitationsPage);
    fixture.componentRef.setInput('editionId', '3');
    await fixture.whenStable();
    const page = fixture.componentInstance as unknown as {
      form: { patchValue(value: object): void };
      send(): Promise<void>;
    };
    page.form.patchValue({ emails: 'pas-une-adresse', role: 'SC_MEMBER' });
    await page.send();
    fixture.detectChanges();
    expect(api['invite']).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('Adresses invalides : pas-une-adresse');
  });

  it('envoi groupé : adresses ignorées signalées, liste rechargée', async () => {
    api['invite'].mockResolvedValue({
      created: [{ id: 1 }],
      skipped: [{ email: 'b***@x.org', reason: 'already_member' }],
    });
    const fixture = TestBed.createComponent(InvitationsPage);
    fixture.componentRef.setInput('editionId', '3');
    await fixture.whenStable();
    const page = fixture.componentInstance as unknown as {
      form: { patchValue(value: object): void };
      send(): Promise<void>;
    };
    page.form.patchValue({ emails: 'a@x.org, b@x.org', role: 'SC_MEMBER', message: ' Merci ' });
    await page.send();
    fixture.detectChanges();
    expect(api['invite']).toHaveBeenCalledWith(3, {
      emails: ['a@x.org', 'b@x.org'],
      role: 'SC_MEMBER',
      oc_function: '',
      locale: 'fr',
      message: 'Merci',
    });
    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Invitations envoyées : 1.');
    expect(text).toContain('rôle déjà actif');
    expect(api['invitations']).toHaveBeenCalledTimes(2);
  });
});

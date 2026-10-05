import { DOCUMENT, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { GcApiError, InvitationLookup, MeStore, SessionStore } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { AccountService } from '../account.service';
import { PendingInvitation } from '../pending-invitation';
import { provideAccountTesting } from '../testing';
import { InvitationPage } from './invitation-page';

const LOOKUP: InvitationLookup = {
  edition_code: 'GC27',
  edition_title_fr: 'GEST-CONF 2027',
  edition_title_en: 'GEST-CONF 2027',
  role: 'SC_MEMBER',
  oc_function: '',
  inviter_name: 'Awa Koné',
  email_masked: 'r***@univ.ci',
  status: 'pending',
  expires_at: '2027-01-10T00:00:00Z',
  message: '',
  controls_address: true,
};

describe('InvitationPage', () => {
  let account: Record<string, ReturnType<typeof vi.fn>>;
  const authenticated = signal(true);

  beforeEach(async () => {
    authenticated.set(true);
    account = {
      lookupInvitation: vi.fn().mockResolvedValue(LOOKUP),
      acceptInvitation: vi.fn().mockResolvedValue({ edition_id: 3, role: 'SC_MEMBER' }),
      acceptInvitationLink: vi.fn().mockResolvedValue({ edition_id: 3, role: 'SC_MEMBER' }),
      declineInvitation: vi.fn().mockResolvedValue(undefined),
      requestInvitationLink: vi.fn().mockResolvedValue(undefined),
    };
    TestBed.configureTestingModule({
      imports: [InvitationPage],
      providers: [
        ...provideAccountTesting(),
        { provide: AccountService, useValue: account },
        { provide: SessionStore, useValue: { authenticated } },
        { provide: MeStore, useValue: { load: vi.fn().mockResolvedValue({}) } },
      ],
    });
    await useTestLanguage('fr');
  });

  afterEach(() => TestBed.inject(PendingInvitation).clear());

  async function render(hash: string) {
    const view = TestBed.inject(DOCUMENT).defaultView!;
    view.history.replaceState(null, '', `/compte/invitation${hash}`);
    const fixture = TestBed.createComponent(InvitationPage);
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture;
  }

  async function click(fixture: Awaited<ReturnType<typeof render>>, label: string) {
    const button = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((item) => item.textContent?.includes(label));
    button!.click();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  it('jeton lu dans le fragment puis effacé de l’adresse ; acceptation', async () => {
    const fixture = await render('#jeton-secret');
    expect(account['lookupInvitation']).toHaveBeenCalledWith('jeton-secret');
    expect(TestBed.inject(DOCUMENT).defaultView!.location.hash).toBe('');
    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Awa Koné vous invite');
    expect(text).toContain('r***@univ.ci');
    await click(fixture, "Accepter l'invitation");
    expect(account['acceptInvitation']).toHaveBeenCalledWith('jeton-secret');
    expect(fixture.nativeElement.textContent).toContain('Bienvenue');
  });

  it('compte sans l’adresse invitée : lien de confirmation proposé (RG-20)', async () => {
    account['lookupInvitation'].mockResolvedValue({ ...LOOKUP, controls_address: false });
    const fixture = await render('#jeton');
    expect(fixture.nativeElement.textContent).not.toContain("Accepter l'invitation");
    await click(fixture, 'Recevoir un lien de confirmation');
    expect(account['requestInvitationLink']).toHaveBeenCalledWith('jeton');
    expect(fixture.nativeElement.textContent).toContain('Un lien de confirmation a été envoyé');
  });

  it('visiteur anonyme : connexion avec retour sur l’invitation, refus possible', async () => {
    authenticated.set(false);
    const fixture = await render('#jeton');
    const login = (fixture.nativeElement as HTMLElement).querySelector(
      'a[href^="/compte/connexion"]',
    );
    expect(login?.getAttribute('href')).toBe('/compte/connexion?next=%2Fcompte%2Finvitation');
    await click(fixture, "Refuser l'invitation");
    expect(account['declineInvitation']).toHaveBeenCalledWith('jeton');
  });

  it('lien de liaison (#lier=…) : acceptation par le lien', async () => {
    const fixture = await render('#lier=lien-signe');
    await click(fixture, "Confirmer l'adresse et accepter");
    expect(account['acceptInvitationLink']).toHaveBeenCalledWith('lien-signe');
    expect(account['lookupInvitation']).not.toHaveBeenCalled();
  });

  it('jeton inconnu : message dédié', async () => {
    account['lookupInvitation'].mockRejectedValue(new GcApiError(404, 'not_found', 'x'));
    const fixture = await render('#inconnu');
    expect(fixture.nativeElement.textContent).toContain('Cette invitation est introuvable');
  });
});

import { TestBed } from '@angular/core/testing';
import { AuthApi, AuthResult } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { provideAccountTesting } from '../testing';
import { VerifyEmailPage } from './verify-email-page';

const OK: AuthResult = {
  status: 401,
  authenticated: false,
  user: null,
  pendingFlow: null,
  errors: [],
};

describe('VerifyEmailPage', () => {
  let verifyEmail: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    verifyEmail = vi.fn().mockResolvedValue(OK);
    TestBed.configureTestingModule({
      imports: [VerifyEmailPage],
      providers: [...provideAccountTesting(), { provide: AuthApi, useValue: { verifyEmail } }],
    });
    await useTestLanguage('fr');
  });

  afterEach(() => history.replaceState(null, '', '/'));

  it('lit la clé du fragment, la vérifie puis l’efface de l’adresse', async () => {
    history.replaceState(null, '', '/compte/verifier-email#MQ%3A1abc%3Axyz');
    const fixture = TestBed.createComponent(VerifyEmailPage);
    await fixture.whenStable();
    fixture.detectChanges();
    expect(verifyEmail).toHaveBeenCalledWith('MQ:1abc:xyz');
    expect(location.hash).toBe('');
    expect(fixture.nativeElement.textContent).toContain('Votre adresse est vérifiée');
  });

  it('clé refusée : message et renvoi par une nouvelle connexion', async () => {
    verifyEmail.mockResolvedValue({
      ...OK,
      status: 400,
      errors: [{ code: 'invalid_or_expired_key', message: 'x', param: 'key' }],
    });
    history.replaceState(null, '', '/compte/verifier-email#cle');
    const fixture = TestBed.createComponent(VerifyEmailPage);
    await fixture.whenStable();
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Ce lien est invalide ou a expiré.');
    expect(text).toContain('Recevoir un nouveau lien');
  });

  it('sans clé : « consultez vos e-mails », aucun appel', async () => {
    const fixture = TestBed.createComponent(VerifyEmailPage);
    await fixture.whenStable();
    expect(verifyEmail).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('Consultez votre messagerie');
  });
});

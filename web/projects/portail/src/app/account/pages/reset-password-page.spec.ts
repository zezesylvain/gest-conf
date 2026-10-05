import { TestBed } from '@angular/core/testing';
import { AuthApi, AuthResult } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { provideAccountTesting } from '../testing';
import { ResetPasswordPage } from './reset-password-page';

const OK: AuthResult = {
  status: 200,
  authenticated: false,
  user: null,
  pendingFlow: null,
  errors: [],
};

describe('ResetPasswordPage', () => {
  let checkPasswordResetKey: ReturnType<typeof vi.fn>;
  let resetPassword: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    checkPasswordResetKey = vi.fn().mockResolvedValue(OK);
    resetPassword = vi.fn().mockResolvedValue({ ...OK, status: 401 });
    TestBed.configureTestingModule({
      imports: [ResetPasswordPage],
      providers: [
        ...provideAccountTesting(),
        { provide: AuthApi, useValue: { checkPasswordResetKey, resetPassword } },
      ],
    });
    await useTestLanguage('fr');
  });

  afterEach(() => history.replaceState(null, '', '/'));

  it('sans clé : lien invalide', async () => {
    const fixture = TestBed.createComponent(ResetPasswordPage);
    await fixture.whenStable();
    expect(checkPasswordResetKey).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('lien de réinitialisation est invalide');
  });

  it('clé valide : nouveau mot de passe enregistré', async () => {
    history.replaceState(null, '', '/compte/reinitialiser#1-abc');
    const fixture = TestBed.createComponent(ResetPasswordPage);
    await fixture.whenStable();
    fixture.detectChanges();
    expect(checkPasswordResetKey).toHaveBeenCalledWith('1-abc');
    expect(location.hash).toBe('');
    const root: HTMLElement = fixture.nativeElement;
    for (const input of Array.from(root.querySelectorAll<HTMLInputElement>('input'))) {
      input.value = 'nouveau-mot-de-passe';
      input.dispatchEvent(new Event('input'));
    }
    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    fixture.detectChanges();
    expect(resetPassword).toHaveBeenCalledWith('1-abc', 'nouveau-mot-de-passe');
    expect(root.textContent).toContain('Votre mot de passe a été modifié');
  });
});

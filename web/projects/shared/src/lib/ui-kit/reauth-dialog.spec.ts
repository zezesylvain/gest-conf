import { TestBed } from '@angular/core/testing';
import { MatDialogRef } from '@angular/material/dialog';
import { provideI18nTesting, TEST_ME, useTestLanguage } from '../../testing';
import { AuthResult } from '../auth/allauth';
import { AuthApi } from '../auth/auth-api';
import { MeStore } from '../auth/me.store';
import { ReauthDialog } from './reauth-dialog';

function result(partial: Partial<AuthResult>): AuthResult {
  return {
    status: 200,
    authenticated: false,
    user: null,
    pendingFlow: null,
    errors: [],
    ...partial,
  };
}

describe('ReauthDialog', () => {
  let reauthenticate: ReturnType<typeof vi.fn>;
  let mfaReauthenticate: ReturnType<typeof vi.fn>;
  let close: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    reauthenticate = vi.fn();
    mfaReauthenticate = vi.fn();
    close = vi.fn();
    TestBed.configureTestingModule({
      imports: [ReauthDialog],
      providers: [
        provideI18nTesting(),
        { provide: AuthApi, useValue: { reauthenticate, mfaReauthenticate } },
        { provide: MatDialogRef, useValue: { close } },
        { provide: MeStore, useValue: { me: () => ({ ...TEST_ME, mfa_enabled: true }) } },
      ],
    });
    await useTestLanguage('fr');
  });

  async function render() {
    const fixture = TestBed.createComponent(ReauthDialog);
    await fixture.whenStable();
    return fixture;
  }

  async function submit(fixture: Awaited<ReturnType<typeof render>>, value: string) {
    const root: HTMLElement = fixture.nativeElement;
    const input = root.querySelector<HTMLInputElement>('input')!;
    input.value = value;
    input.dispatchEvent(new Event('input'));
    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    fixture.detectChanges();
  }

  it('mot de passe accepté : fenêtre fermée sur « true »', async () => {
    reauthenticate.mockResolvedValue(result({ authenticated: true }));
    await submit(await render(), 'motdepasse-solide');
    expect(reauthenticate).toHaveBeenCalledWith('motdepasse-solide');
    expect(close).toHaveBeenCalledWith(true);
  });

  it('compte 2FA : bascule vers le code', async () => {
    mfaReauthenticate.mockResolvedValue(result({ authenticated: true }));
    const fixture = await render();
    const root: HTMLElement = fixture.nativeElement;
    root.querySelector<HTMLButtonElement>('.link-button')!.click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(root.querySelector('input')?.getAttribute('autocomplete')).toBe('one-time-code');
    await submit(fixture, '123456');
    expect(mfaReauthenticate).toHaveBeenCalledWith('123456');
    expect(close).toHaveBeenCalledWith(true);
  });

  it('mot de passe refusé : message, fenêtre ouverte', async () => {
    reauthenticate.mockResolvedValue(
      result({
        status: 400,
        authenticated: true,
        errors: [{ code: 'incorrect_password', message: 'X', param: 'password' }],
      }),
    );
    const fixture = await render();
    await submit(fixture, 'faux');
    expect(fixture.nativeElement.textContent).toContain('Mot de passe incorrect.');
    expect(close).not.toHaveBeenCalled();
  });
});

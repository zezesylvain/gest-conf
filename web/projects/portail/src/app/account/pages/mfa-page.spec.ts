import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, Router } from '@angular/router';
import { AuthApi, AuthResult, MeStore, SessionStore } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { provideAccountTesting } from '../testing';
import { MfaPage } from './mfa-page';

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

describe('MfaPage', () => {
  let mfaAuthenticate: ReturnType<typeof vi.fn>;
  let mfaReauthenticate: ReturnType<typeof vi.fn>;
  const authenticated = signal(false);

  beforeEach(async () => {
    mfaAuthenticate = vi.fn();
    mfaReauthenticate = vi.fn();
    authenticated.set(false);
    TestBed.configureTestingModule({
      imports: [MfaPage],
      providers: [
        ...provideAccountTesting(),
        { provide: AuthApi, useValue: { mfaAuthenticate, mfaReauthenticate } },
        { provide: SessionStore, useValue: { authenticated } },
        { provide: MeStore, useValue: { load: vi.fn().mockResolvedValue({}) } },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: convertToParamMap({ next: '/compte/profil' }) } },
        },
      ],
    });
    await useTestLanguage('fr');
  });

  async function submit(code: string) {
    const fixture = TestBed.createComponent(MfaPage);
    await fixture.whenStable();
    const root: HTMLElement = fixture.nativeElement;
    const input = root.querySelector<HTMLInputElement>('input')!;
    expect(input.getAttribute('autocomplete')).toBe('one-time-code');
    input.value = code;
    input.dispatchEvent(new Event('input'));
    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    fixture.detectChanges();
    return root;
  }

  it('étape 2FA de la connexion, puis suite vers « next »', async () => {
    mfaAuthenticate.mockResolvedValue(result({ authenticated: true }));
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    await submit('123 456');
    expect(mfaAuthenticate).toHaveBeenCalledWith('123456');
    expect(navigate).toHaveBeenCalledWith('/compte/profil');
  });

  it('session ouverte : réauthentification 2FA (step-up)', async () => {
    authenticated.set(true);
    mfaReauthenticate.mockResolvedValue(result({ authenticated: true }));
    vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    const root = await submit('654321');
    expect(root.textContent).toContain('espace de gestion');
    expect(mfaReauthenticate).toHaveBeenCalledWith('654321');
    expect(mfaAuthenticate).not.toHaveBeenCalled();
  });

  it('code incorrect : message traduit sur le champ', async () => {
    mfaAuthenticate.mockResolvedValue(
      result({ status: 400, errors: [{ code: 'incorrect_code', message: 'X', param: 'code' }] }),
    );
    const root = await submit('000000');
    expect(root.textContent).toContain('Code incorrect.');
  });
});

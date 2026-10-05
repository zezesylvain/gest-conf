import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { AuthApi, AuthResult } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { provideAccountTesting } from '../testing';
import { SignupPage } from './signup-page';

const PENDING: AuthResult = {
  status: 401,
  authenticated: false,
  user: null,
  pendingFlow: 'verify_email',
  errors: [],
};

describe('SignupPage', () => {
  let signup: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    signup = vi.fn().mockResolvedValue(PENDING);
    TestBed.configureTestingModule({
      imports: [SignupPage],
      providers: [...provideAccountTesting(), { provide: AuthApi, useValue: { signup } }],
    });
    await useTestLanguage('fr');
  });

  afterEach(() => vi.restoreAllMocks());

  async function submit(email: string, password: string, confirm: string) {
    const fixture = TestBed.createComponent(SignupPage);
    await fixture.whenStable();
    const root: HTMLElement = fixture.nativeElement;
    const [emailInput, passwordInput, confirmInput] = Array.from(
      root.querySelectorAll<HTMLInputElement>('input'),
    );
    for (const [input, value] of [
      [emailInput, email],
      [passwordInput, password],
      [confirmInput, confirm],
    ] as const) {
      input.value = value;
      input.dispatchEvent(new Event('input'));
    }
    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    fixture.detectChanges();
    return root;
  }

  it('affiche la notice d’information', async () => {
    const fixture = TestBed.createComponent(SignupPage);
    await fixture.whenStable();
    expect(fixture.nativeElement.querySelector('portail-privacy-notice')).not.toBeNull();
  });

  it('mots de passe différents ou trop courts : aucun appel', async () => {
    const root = await submit('awa@univ.ci', 'motdepasse-solide', 'autre-chose-xx');
    expect(signup).not.toHaveBeenCalled();
    expect(root.textContent).toContain('ne correspondent pas');
    await submit('awa@univ.ci', 'court', 'court');
    expect(signup).not.toHaveBeenCalled();
  });

  it('inscription : écran « consultez vos e-mails », que l’adresse existe ou non', async () => {
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    await submit('awa@univ.ci', 'motdepasse-solide', 'motdepasse-solide');
    expect(signup).toHaveBeenCalledWith('awa@univ.ci', 'motdepasse-solide');
    expect(navigate).toHaveBeenCalledWith(['/compte/verifier-email'], {
      state: { email: 'awa@univ.ci' },
    });
  });

  it('mot de passe refusé par le serveur : erreur traduite sur le champ', async () => {
    signup.mockResolvedValue({
      ...PENDING,
      status: 400,
      pendingFlow: null,
      errors: [{ code: 'password_too_common', message: 'x', param: 'password' }],
    });
    const root = await submit('awa@univ.ci', 'motdepasse123', 'motdepasse123');
    expect(root.textContent).toContain('Ce mot de passe est trop courant.');
  });
});

import { DOCUMENT } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap, Router } from '@angular/router';
import { AuthApi, AuthResult } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { provideAccountTesting } from '../testing';
import { LoginPage } from './login-page';

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

describe('LoginPage', () => {
  let login: ReturnType<typeof vi.fn>;
  let next: string | null;

  beforeEach(async () => {
    login = vi.fn();
    next = null;
    TestBed.configureTestingModule({
      imports: [LoginPage],
      providers: [
        ...provideAccountTesting(),
        { provide: AuthApi, useValue: { login } },
        {
          provide: ActivatedRoute,
          useFactory: () => ({
            snapshot: { queryParamMap: convertToParamMap(next ? { next } : {}) },
          }),
        },
      ],
    });
    await useTestLanguage('fr');
  });

  afterEach(() => vi.restoreAllMocks());

  async function render() {
    const fixture = TestBed.createComponent(LoginPage);
    await fixture.whenStable();
    return fixture;
  }

  async function fill(
    fixture: Awaited<ReturnType<typeof render>>,
    email: string,
    password: string,
  ) {
    const root: HTMLElement = fixture.nativeElement;
    const inputs = root.querySelectorAll<HTMLInputElement>('input');
    inputs[0].value = email;
    inputs[0].dispatchEvent(new Event('input'));
    inputs[1].value = password;
    inputs[1].dispatchEvent(new Event('input'));
    root.querySelector<HTMLFormElement>('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    fixture.detectChanges();
  }

  it('champs étiquetés, avec autocomplétion', async () => {
    const root: HTMLElement = (await render()).nativeElement;
    expect(root.querySelector('h1')?.textContent).toContain('Connexion');
    const email = root.querySelector<HTMLInputElement>('input[type=email]');
    expect(email?.getAttribute('autocomplete')).toBe('email');
    expect(root.querySelector('input[type=password]')?.getAttribute('autocomplete')).toBe(
      'current-password',
    );
  });

  it('formulaire invalide : aucun appel, erreurs affichées', async () => {
    const fixture = await render();
    await fill(fixture, 'pas-une-adresse', '');
    expect(login).not.toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('Ce champ est obligatoire.');
  });

  it('connexion réussie : suite vers « next » validé', async () => {
    next = '/compte/profil';
    login.mockResolvedValue(result({ authenticated: true }));
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    const fixture = await render();
    await fill(fixture, 'awa@univ.ci', 'motdepasse-solide');
    expect(login).toHaveBeenCalledWith('awa@univ.ci', 'motdepasse-solide');
    expect(navigate).toHaveBeenCalledWith('/compte/profil');
  });

  it('« next » malveillant ignoré : retour à /compte', async () => {
    next = 'https://pirate.example/';
    login.mockResolvedValue(result({ authenticated: true }));
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    await fill(await render(), 'awa@univ.ci', 'motdepasse-solide');
    expect(navigate).toHaveBeenCalledWith('/compte');
  });

  it('vers la gestion : navigation de page entière', async () => {
    next = '/gestion/';
    login.mockResolvedValue(result({ authenticated: true }));
    const assign = vi.fn();
    const document = TestBed.inject(DOCUMENT);
    // Fenêtre réelle, sauf location.assign (non implémentée par jsdom).
    const view = new Proxy(window, {
      get: (target, property) => {
        if (property === 'location') {
          return { assign };
        }
        const value = Reflect.get(target, property);
        return typeof value === 'function' ? value.bind(target) : value;
      },
    });
    vi.spyOn(document, 'defaultView', 'get').mockReturnValue(view);
    await fill(await render(), 'awa@univ.ci', 'motdepasse-solide');
    expect(assign).toHaveBeenCalledWith('/gestion/');
  });

  it('adresse non vérifiée : message « consultez vos e-mails »', async () => {
    login.mockResolvedValue(result({ status: 401, pendingFlow: 'verify_email' }));
    const fixture = await render();
    await fill(fixture, 'awa@univ.ci', 'motdepasse-solide');
    expect(fixture.nativeElement.textContent).toContain('pas encore vérifiée');
  });

  it('identifiants refusés : message traduit sur le champ du mot de passe', async () => {
    login.mockResolvedValue(
      result({
        status: 400,
        errors: [{ code: 'email_password_mismatch', message: 'Server', param: 'password' }],
      }),
    );
    const fixture = await render();
    await fill(fixture, 'awa@univ.ci', 'mauvais');
    expect(fixture.nativeElement.textContent).toContain(
      'Adresse e-mail ou mot de passe incorrect.',
    );
  });
});

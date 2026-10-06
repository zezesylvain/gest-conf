import { DOCUMENT } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { AuthApi } from '@gestconf/shared';
import { provideAuthTesting, useTestLanguage } from '@gestconf/shared/testing';

import { AccountShell } from './account-shell';
import { NotificationsStore } from './notifications/notifications.store';
import { THEME_STYLESHEET } from './theme';
import { provideAccountTesting } from './testing';

describe('AccountShell', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      imports: [AccountShell],
      providers: [
        ...provideAccountTesting(),
        ...provideAuthTesting(),
        { provide: AuthApi, useValue: { logout: vi.fn().mockResolvedValue({}) } },
        {
          provide: NotificationsStore,
          useValue: { unread: () => 3, refresh: vi.fn().mockResolvedValue(undefined) },
        },
      ],
    });
    await useTestLanguage('fr');
  });

  it('charge le thème Material à la demande et marque l’espace en noindex', async () => {
    const document = TestBed.inject(DOCUMENT);
    const fixture = TestBed.createComponent(AccountShell);
    await fixture.whenStable();
    const links = document.querySelectorAll(`link[href="${THEME_STYLESHEET}"]`);
    expect(links.length).toBe(1);
    expect(document.querySelector('meta[name="robots"]')?.getAttribute('content')).toContain(
      'noindex',
    );
    // Un second affichage n'ajoute pas de seconde feuille.
    TestBed.createComponent(AccountShell);
    expect(document.querySelectorAll(`link[href="${THEME_STYLESHEET}"]`).length).toBe(1);
    fixture.destroy();
    expect(document.querySelector('meta[name="robots"]')).toBeNull();
  });

  it('navigation du compte et déconnexion pour une session ouverte', async () => {
    const fixture = TestBed.createComponent(AccountShell);
    await fixture.whenStable();
    const text = fixture.nativeElement.textContent;
    expect(text).toContain('Profil');
    expect(text).toContain('Se déconnecter');
  });

  it('cloche : nombre de non lues, libellé accessible, relu à l’ouverture', async () => {
    const fixture = TestBed.createComponent(AccountShell);
    await fixture.whenStable();
    fixture.detectChanges();
    const bell = (fixture.nativeElement as HTMLElement).querySelector<HTMLAnchorElement>(
      'a[href="/compte/notifications"]',
    )!;
    expect(bell.textContent).toContain('3');
    expect(bell.getAttribute('aria-label')).toBe('Notifications (3 non lue(s))');
    expect(TestBed.inject(NotificationsStore).refresh).toHaveBeenCalled();
  });
});

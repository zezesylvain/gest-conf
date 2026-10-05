import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideI18nTesting, useTestLanguage } from '@gestconf/shared/testing';

import { App } from './app';

describe('App (portail)', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      imports: [App],
      providers: [
        provideRouter([]),
        provideI18nTesting({
          fr: () => import('../i18n/fr.json'),
          en: () => import('../i18n/en.json'),
        }),
      ],
    });
    await useTestLanguage('fr');
  });

  it('affiche l’en-tête, le sélecteur de langue et un lien d’évitement vers le contenu', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const root: HTMLElement = fixture.nativeElement;

    const skipLink = root.querySelector<HTMLAnchorElement>('.skip-link');
    expect(skipLink?.getAttribute('href')).toBe('#contenu');
    expect(skipLink?.textContent).toContain('Aller au contenu');
    expect(root.querySelector('main#contenu')).not.toBeNull();
    expect(root.querySelector('.brand')?.textContent).toContain('GEST-CONF');
    expect(root.querySelector('gc-language-switcher')).not.toBeNull();
  });
});

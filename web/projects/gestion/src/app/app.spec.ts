import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideI18nTesting, useTestLanguage } from '@gestconf/shared/testing';

import { App } from './app';

describe('App (gestion)', () => {
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

  it('affiche l’en-tête de l’espace de gestion et un lien d’évitement', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const root: HTMLElement = fixture.nativeElement;

    expect(root.querySelector('.brand')?.textContent).toContain('GEST-CONF · Gestion');
    expect(root.querySelector('.skip-link')?.getAttribute('href')).toBe('#contenu');
    expect(root.querySelector('main#contenu')).not.toBeNull();
  });
});

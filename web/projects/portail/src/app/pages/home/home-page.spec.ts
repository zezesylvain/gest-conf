import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideI18nTesting, useTestLanguage } from '@gestconf/shared/testing';

import { HomePage } from './home-page';

describe('HomePage', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      imports: [HomePage],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideI18nTesting({
          fr: () => import('../../../i18n/fr.json'),
          en: () => import('../../../i18n/en.json'),
        }),
      ],
    });
  });

  it('affiche le titre traduit et un lien vers l’application de gestion', async () => {
    await useTestLanguage('en');
    const fixture = TestBed.createComponent(HomePage);
    await fixture.whenStable();
    const root: HTMLElement = fixture.nativeElement;

    expect(root.querySelector('h1')?.textContent).toContain('Scientific conference');
    expect(root.querySelector('a.cta')?.getAttribute('href')).toBe('/gestion/');
    expect(root.querySelector('gc-api-status')).not.toBeNull();

    TestBed.inject(HttpTestingController).match('/api/v1/health');
  });
});

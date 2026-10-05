import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideI18nTesting, useTestLanguage } from '@gestconf/shared/testing';

import { DashboardPage } from './dashboard-page';

describe('DashboardPage', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      imports: [DashboardPage],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideI18nTesting({
          fr: () => import('../../../i18n/fr.json'),
          en: () => import('../../../i18n/en.json'),
        }),
      ],
    });
    await useTestLanguage('fr');
  });

  it('affiche le titre traduit et l’état de l’API', async () => {
    const fixture = TestBed.createComponent(DashboardPage);
    await fixture.whenStable();
    const root: HTMLElement = fixture.nativeElement;

    expect(root.querySelector('h1')?.textContent).toContain('Espace de gestion');
    expect(root.querySelector('gc-api-status')).not.toBeNull();

    TestBed.inject(HttpTestingController).match('/api/v1/health');
  });
});

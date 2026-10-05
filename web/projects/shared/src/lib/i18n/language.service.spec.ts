import { DOCUMENT } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { TranslateService } from '@ngx-translate/core';

import { provideI18nTesting } from '../../testing';
import { LanguageService } from './language.service';

describe('LanguageService', () => {
  let service: LanguageService;
  let document: Document;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({ providers: [provideI18nTesting()] });
    service = TestBed.inject(LanguageService);
    document = TestBed.inject(DOCUMENT);
  });

  it('applique la langue choisie au document et la mémorise', async () => {
    await service.use('en');
    expect(service.current()).toBe('en');
    expect(document.documentElement.lang).toBe('en');
    expect(localStorage.getItem('gestconf.lang')).toBe('en');
    expect(TestBed.inject(TranslateService).instant('shared.apiStatus.ok')).toBe('API operational');
  });

  it('reprend au démarrage la langue mémorisée', async () => {
    localStorage.setItem('gestconf.lang', 'en');
    await service.init();
    expect(service.current()).toBe('en');
  });

  it('ignore une valeur mémorisée invalide', async () => {
    localStorage.setItem('gestconf.lang', 'xx');
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('fr-CI');
    await service.init();
    expect(service.current()).toBe('fr');
  });

  it('ne mémorise pas la langue détectée au démarrage', async () => {
    await service.init();
    expect(localStorage.getItem('gestconf.lang')).toBeNull();
  });
});

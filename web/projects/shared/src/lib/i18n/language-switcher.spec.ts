import { TestBed } from '@angular/core/testing';

import { provideI18nTesting, useTestLanguage } from '../../testing';
import { LanguageSwitcher } from './language-switcher';
import { LanguageService } from './language.service';

describe('LanguageSwitcher', () => {
  beforeEach(async () => {
    localStorage.clear();
    TestBed.configureTestingModule({
      imports: [LanguageSwitcher],
      providers: [provideI18nTesting()],
    });
    await useTestLanguage('fr');
  });

  it('indique la langue active et permet d’en changer', async () => {
    const fixture = TestBed.createComponent(LanguageSwitcher);
    await fixture.whenStable();
    const [fr, en] = Array.from(
      fixture.nativeElement.querySelectorAll('button'),
    ) as HTMLButtonElement[];
    expect(fr.getAttribute('aria-pressed')).toBe('true');
    expect(en.getAttribute('lang')).toBe('en');

    en.click();
    await vi.waitFor(() => expect(TestBed.inject(LanguageService).current()).toBe('en'));
    await fixture.whenStable();
    expect(en.getAttribute('aria-pressed')).toBe('true');
    expect(fixture.nativeElement.querySelector('[role="group"]').getAttribute('aria-label')).toBe(
      'Language',
    );
  });
});

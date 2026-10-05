import { TestBed } from '@angular/core/testing';
import { useTestLanguage } from '@gestconf/shared/testing';

import { AccountService } from '../account.service';
import { provideAccountTesting } from '../testing';
import { PrivacyPage } from './privacy-page';

const STATE = (granted: boolean) => ({
  states: [
    {
      kind: 'directory_listing',
      granted,
      text_version: 'v0',
      recorded_at: null,
      current_text_version: 'v0',
    },
  ],
  history: [],
});

describe('PrivacyPage', () => {
  it('consentement facultatif accordé puis retirable', async () => {
    const account = {
      consents: vi.fn().mockResolvedValueOnce(STATE(false)).mockResolvedValue(STATE(true)),
      setConsent: vi.fn().mockResolvedValue({}),
    };
    TestBed.configureTestingModule({
      imports: [PrivacyPage],
      providers: [...provideAccountTesting(), { provide: AccountService, useValue: account }],
    });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(PrivacyPage);
    await fixture.whenStable();
    fixture.detectChanges();
    const root: HTMLElement = fixture.nativeElement;
    expect(root.textContent).toContain("Vous n'apparaissez pas dans l'annuaire.");
    Array.from(root.querySelectorAll('button'))
      .find((button) => button.textContent?.includes("Apparaître dans l'annuaire"))!
      .click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(account.setConsent).toHaveBeenCalledWith('directory_listing', true);
    expect(root.textContent).toContain('Retirer mon accord');
  });

  it('photo : second consentement facultatif, indépendant de l’annuaire', async () => {
    const consents = {
      states: [
        ...STATE(true).states,
        {
          kind: 'photo_publication',
          granted: false,
          text_version: 'v0',
          recorded_at: null,
          current_text_version: 'v0',
        },
      ],
      history: [],
    };
    const account = {
      consents: vi.fn().mockResolvedValue(consents),
      setConsent: vi.fn().mockResolvedValue({}),
    };
    TestBed.configureTestingModule({
      imports: [PrivacyPage],
      providers: [...provideAccountTesting(), { provide: AccountService, useValue: account }],
    });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(PrivacyPage);
    await fixture.whenStable();
    fixture.detectChanges();
    const root: HTMLElement = fixture.nativeElement;
    expect(root.textContent).toContain("Votre photo n'est pas publiée.");
    Array.from(root.querySelectorAll('button'))
      .find((button) => button.textContent?.includes('Publier ma photo'))!
      .click();
    await fixture.whenStable();
    expect(account.setConsent).toHaveBeenCalledWith('photo_publication', true);
  });
});

import { TestBed } from '@angular/core/testing';
import { AuthApi, AuthResult, MeStore } from '@gestconf/shared';
import { TEST_ME, useTestLanguage } from '@gestconf/shared/testing';

import { AccountService } from '../../account.service';
import { provideAccountTesting } from '../../testing';
import { MfaSection } from './mfa-section';

function result(partial: Partial<AuthResult>): AuthResult {
  return {
    status: 200,
    authenticated: true,
    user: null,
    pendingFlow: null,
    errors: [],
    ...partial,
  };
}

const TOTP = { type: 'totp', created_at: 1, last_used_at: null };
const RECOVERY = {
  type: 'recovery_codes',
  created_at: 1,
  last_used_at: null,
  total_code_count: 10,
  unused_code_count: 10,
};

describe('MfaSection', () => {
  let api: Record<string, ReturnType<typeof vi.fn>>;

  beforeEach(async () => {
    api = {
      authenticators: vi.fn().mockResolvedValue([]),
      totpSetup: vi.fn(),
      activateTotp: vi.fn(),
      recoveryCodes: vi.fn(),
      regenerateRecoveryCodes: vi.fn(),
      deactivateTotp: vi.fn(),
    };
    TestBed.configureTestingModule({
      imports: [MfaSection],
      providers: [
        ...provideAccountTesting(),
        { provide: AuthApi, useValue: api },
        {
          provide: AccountService,
          useValue: { totpQrCode: vi.fn().mockResolvedValue('data:image/svg+xml;base64,PHN2Zy8+') },
        },
        {
          provide: MeStore,
          useValue: { me: () => TEST_ME, load: vi.fn().mockResolvedValue(TEST_ME) },
        },
      ],
    });
    await useTestLanguage('fr');
  });

  async function render() {
    const fixture = TestBed.createComponent(MfaSection);
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture;
  }

  async function click(fixture: Awaited<ReturnType<typeof render>>, label: string) {
    const button = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('button'),
    ).find((item) => item.textContent?.includes(label));
    button!.click();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  it('activation : QR code et clé, puis codes de secours affichés', async () => {
    api['totpSetup'].mockResolvedValue({
      setup: { secret: 'JBSWY3DP', totpUrl: 'otpauth://totp/x' },
      result: result({ status: 404 }),
    });
    api['activateTotp'].mockResolvedValue(result({}));
    api['recoveryCodes'].mockResolvedValue({ ...RECOVERY, unused_codes: ['11112222'] });
    const fixture = await render();
    const root: HTMLElement = fixture.nativeElement;
    expect(root.textContent).toContain("n'est pas activée");
    await click(fixture, 'Activer la double authentification');
    const image = root.querySelector('img');
    expect(image?.getAttribute('src')).toContain('data:image/svg+xml');
    expect(image?.getAttribute('alt')).toContain('QR code');
    expect(root.textContent).toContain('JBSWY3DP');
    api['authenticators'].mockResolvedValue([TOTP, RECOVERY]);
    const input = root.querySelector<HTMLInputElement>('input')!;
    input.value = '123456';
    input.dispatchEvent(new Event('input'));
    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    fixture.detectChanges();
    expect(api['activateTotp']).toHaveBeenCalledWith('123456');
    expect(root.textContent).toContain('11112222');
    expect(root.textContent).toContain('est activée');
  });

  it('adresse non vérifiée : activation impossible, message explicite', async () => {
    api['totpSetup'].mockResolvedValue({
      setup: null,
      result: result({ status: 409, errors: [{ code: 'unverified_email', message: 'X' }] }),
    });
    const fixture = await render();
    await click(fixture, 'Activer la double authentification');
    expect(fixture.nativeElement.textContent).toContain('Vérifiez d');
  });

  it('désactivation après confirmation', async () => {
    api['authenticators'].mockResolvedValue([TOTP, RECOVERY]);
    api['deactivateTotp'].mockResolvedValue(result({}));
    const fixture = await render();
    await click(fixture, 'Désactiver…');
    api['authenticators'].mockResolvedValue([]);
    await click(fixture, 'Confirmer la désactivation');
    expect(api['deactivateTotp']).toHaveBeenCalledTimes(1);
    expect(fixture.nativeElement.textContent).toContain('Double authentification désactivée.');
  });
});

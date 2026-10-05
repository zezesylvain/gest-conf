import { DOCUMENT } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { GcApiError, MeStore } from '@gestconf/shared';
import { TEST_ME, useTestLanguage } from '@gestconf/shared/testing';

import { AccountService } from '../account.service';
import { provideAccountTesting } from '../testing';
import { MyDataPage } from './my-data-page';

describe('MyDataPage', () => {
  let account: Record<string, ReturnType<typeof vi.fn>>;

  beforeEach(async () => {
    account = { exportData: vi.fn(), anonymize: vi.fn() };
    TestBed.configureTestingModule({
      imports: [MyDataPage],
      providers: [
        ...provideAccountTesting(),
        { provide: AccountService, useValue: account },
        { provide: MeStore, useValue: { me: () => TEST_ME } },
      ],
    });
    await useTestLanguage('fr');
  });

  afterEach(() => vi.restoreAllMocks());

  async function render() {
    const fixture = TestBed.createComponent(MyDataPage);
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture;
  }

  it('export : fichier JSON téléchargé', async () => {
    account['exportData'].mockResolvedValue({ format: 'gestconf-export-v1' });
    const view = TestBed.inject(DOCUMENT).defaultView!;
    view.URL.createObjectURL = vi.fn().mockReturnValue('blob:x');
    view.URL.revokeObjectURL = vi.fn();
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined);
    const fixture = await render();
    (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('button')!.click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(click).toHaveBeenCalled();
    expect(fixture.nativeElement.textContent).toContain('Export téléchargé.');
  });

  it('anonymisation : confirmation exigée, puis refus « rôles actifs » affiché', async () => {
    account['anonymize'].mockRejectedValue(
      new GcApiError(409, 'account_has_active_duties', 'Non.', { roles: ['GC27:CHAIR'] }),
    );
    const fixture = await render();
    const root: HTMLElement = fixture.nativeElement;
    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    expect(account['anonymize']).not.toHaveBeenCalled();
    const input = root.querySelector<HTMLInputElement>('input[type=email]')!;
    input.value = TEST_ME.email;
    input.dispatchEvent(new Event('input'));
    root.querySelector<HTMLInputElement>('input[type=checkbox]')!.click();
    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    fixture.detectChanges();
    expect(account['anonymize']).toHaveBeenCalledWith(TEST_ME.email);
    expect(root.textContent).toContain('Transmettez');
    expect(root.textContent).toContain('GC27:CHAIR');
  });
});

import { TestBed } from '@angular/core/testing';
import { Meta } from '@angular/platform-browser';
import { ActivatedRoute, convertToParamMap, ParamMap, Router } from '@angular/router';
import { GcApiError, PublicVerification } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';
import { BehaviorSubject } from 'rxjs';

import { DocumentsService } from '../../account/documents/documents.service';
import { provideAccountTesting } from '../../account/testing';
import { normalizeCode, VerificationPage } from './verification-page';

function text(root: HTMLElement): string {
  return (root.textContent ?? '').replace(/[\u00a0\u202f]/g, ' ').replace(/\s+/g, ' ');
}

async function settle(fixture: { detectChanges(): void }): Promise<void> {
  for (let i = 0; i < 5; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  fixture.detectChanges();
}

function verification(overrides: Partial<PublicVerification> = {}): PublicVerification {
  return {
    kind: 'certificate',
    nature: 'participation',
    status: 'valid',
    name: 'Awa Koné',
    edition_title_fr: 'GEST-CONF 2027',
    edition_title_en: 'GEST-CONF 2027',
    edition_start: '2027-06-01',
    edition_end: '2027-06-03',
    issued_at: '2027-06-04T10:00:00Z',
    revoked_at: null,
    ...overrides,
  };
}

describe('Vérification publique (plan L7, K10)', () => {
  let verify: ReturnType<typeof vi.fn>;
  let params: BehaviorSubject<ParamMap>;

  async function render(code: string | null, result: unknown) {
    verify = vi.fn();
    if (result instanceof Error) {
      verify.mockRejectedValue(result);
    } else {
      verify.mockResolvedValue(result);
    }
    params = new BehaviorSubject(convertToParamMap(code ? { code } : {}));
    TestBed.configureTestingModule({
      providers: [
        ...provideAccountTesting(),
        { provide: DocumentsService, useValue: { verify } },
        { provide: ActivatedRoute, useValue: { paramMap: params.asObservable() } },
      ],
    });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(VerificationPage);
    fixture.detectChanges();
    await settle(fixture);
    return { fixture, root: fixture.nativeElement as HTMLElement };
  }

  afterEach(() => TestBed.inject(Meta).removeTag('name="robots"'));

  it('attestation valide : nature, titulaire, conférence, date ; page non indexée', async () => {
    const { root } = await render('abcd-efgh 2345', verification());
    expect(verify).toHaveBeenCalledWith('ABCDEFGH2345');
    expect(text(root)).toContain('Attestation authentique');
    expect(text(root)).toContain('Attestation de participation');
    expect(text(root)).toContain('Awa Koné');
    expect(text(root)).toContain('1 juin 2027 → 3 juin 2027');
    expect(root.querySelector('.result.valid')).not.toBeNull();
    expect(TestBed.inject(Meta).getTag('name="robots"')?.content).toBe('noindex, nofollow');
  });

  it('révoquée, et titulaire anonymisé : statut et date de révocation, sans nom', async () => {
    const { root } = await render(
      'ABCDEF',
      verification({ status: 'revoked', revoked_at: '2027-06-05T10:00:00Z', name: null }),
    );
    expect(text(root)).toContain('Attestation révoquée');
    expect(text(root)).toContain('Non communiqué');
    expect(text(root)).toContain('Révoqué le');
    expect(root.querySelector('.result.revoked')).not.toBeNull();
  });

  it('lettre d’invitation : libellé propre', async () => {
    const { root } = await render('ABCDEF', verification({ kind: 'letter', nature: 'letter' }));
    expect(text(root)).toContain("Lettre d'invitation authentique");
  });

  it('code inconnu ou mal formé : même message, sans détail', async () => {
    const { root } = await render('INCONNU', null);
    expect(text(root)).toContain('Aucun document ne correspond à ce code');
  });

  it('débit dépassé : message du code d’erreur', async () => {
    const { root } = await render('ABCDEF', new GcApiError(429, 'throttled', 'Trop de requêtes'));
    expect(root.querySelector('[role=alert]')).not.toBeNull();
    expect(text(root)).not.toContain('Aucun document ne correspond');
  });

  it('saisie d’un code : adresse de vérification normalisée', async () => {
    const { fixture, root } = await render(null, null);
    expect(verify).not.toHaveBeenCalled();
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const input = root.querySelector('input')!;
    input.value = ' abcd efgh ';
    input.dispatchEvent(new Event('input'));
    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await settle(fixture);
    expect(navigate).toHaveBeenCalledWith(['/verification', 'ABCDEFGH']);
    expect(normalizeCode('ab-cd 23')).toBe('ABCD23');
  });
});

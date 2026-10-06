import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { ActivatedRoute, convertToParamMap, Router } from '@angular/router';
import { GcApiError, MeStore, MyRegistration } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';
import { of } from 'rxjs';

import { RegistrationData } from '../../site/registration/registration-data';
import { CATALOG, myRegistration } from '../../site/registration/testing';
import { provideAccountTesting } from '../testing';
import { PaymentRedirect, RegistrationPage } from './registration-page';
import { RegistrationService } from './registration.service';

function text(root: HTMLElement): string {
  return (root.textContent ?? '').replace(/[\u00a0\u202f]/g, ' ');
}

/** Laisse finir les promesses en chaîne (lectures simulées), puis rend. */
async function settle(fixture: { detectChanges(): void }): Promise<void> {
  for (let i = 0; i < 5; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
  fixture.detectChanges();
}

function button(root: HTMLElement, label: string): HTMLButtonElement | undefined {
  return Array.from(root.querySelectorAll<HTMLButtonElement>('button')).find((item) =>
    item.textContent!.includes(label),
  );
}

interface Page {
  orderForm: { patchValue(v: object): void; controls: { method: { value: string } } };
  computeQuote(): Promise<void>;
  placeOrder(): Promise<void>;
  categoryChanged(): void;
  toggleOption(code: string, checked: boolean): void;
}

describe('« Mon inscription » (plan L6, J13 ; RG-15)', () => {
  let service: Record<string, ReturnType<typeof vi.fn>>;
  let redirect: { go: ReturnType<typeof vi.fn> };
  let navigate: ReturnType<typeof vi.spyOn>;
  /** Réponse de l'interrogation du prestataire au retour de la page de paiement. */
  let check = { outcome: 'confirmed', status: 'confirmed' };

  beforeEach(() => {
    check = { outcome: 'confirmed', status: 'confirmed' };
  });

  async function render(
    registrations: MyRegistration[] = [],
    query: Record<string, string> = {},
    catalog: () => Promise<unknown> = () => Promise.resolve(CATALOG),
  ) {
    service = {
      list: vi.fn().mockResolvedValue(registrations),
      get: vi
        .fn()
        .mockImplementation(() =>
          Promise.resolve(
            check.status === 'confirmed'
              ? myRegistration({ status: 'confirmed', has_qr: true })
              : myRegistration({ method: 'online' }),
          ),
        ),
      quote: vi.fn().mockResolvedValue({
        category: 'researcher',
        currency: 'XOF',
        period: 'regular',
        zone: 'local',
        total: '60000.00',
        lines: [
          {
            kind: 'registration',
            code: 'researcher',
            label_fr: 'Inscription Chercheur',
            label_en: '',
            amount: '50000.00',
          },
          {
            kind: 'option',
            code: 'gala',
            label_fr: 'Dîner de gala',
            label_en: '',
            amount: '10000.00',
          },
        ],
      }),
      order: vi.fn().mockResolvedValue(myRegistration()),
      pay: vi.fn().mockResolvedValue({ payment_url: 'https://pay.test/p/1', reference: 'P1' }),
      paymentCheck: vi.fn().mockImplementation(() => Promise.resolve(check)),
      proforma: vi.fn().mockResolvedValue({}),
      cancel: vi.fn().mockResolvedValue(myRegistration({ status: 'cancelled' })),
      uploadProof: vi.fn(),
      updateBilling: vi.fn(),
    };
    redirect = { go: vi.fn() };
    TestBed.configureTestingModule({
      providers: [
        ...provideAccountTesting(),
        { provide: RegistrationService, useValue: service },
        { provide: RegistrationData, useValue: { catalog: vi.fn(catalog) } },
        { provide: PaymentRedirect, useValue: redirect },
        { provide: MeStore, useValue: { me: () => ({ profile_complete: true }) } },
        { provide: MatDialog, useValue: { open: () => ({ afterClosed: () => of(true) }) } },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParamMap: convertToParamMap(query) } },
        },
      ],
    });
    navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(RegistrationPage);
    fixture.detectChanges();
    await settle(fixture);
    return { fixture, root: fixture.nativeElement as HTMLElement };
  }

  it('commande : prix calculé par le serveur, puis commande par virement (sans redirection)', async () => {
    const { fixture, root } = await render();
    expect(text(root)).toContain("S'inscrire");
    const page = fixture.componentInstance as unknown as Page;
    page.orderForm.patchValue({ category: 'researcher' });
    fixture.detectChanges();
    page.toggleOption('gala', true);
    page.orderForm.patchValue({ promo_code: ' etu ' });
    await page.computeQuote();
    fixture.detectChanges();
    expect(service['quote']).toHaveBeenCalledWith({
      category: 'researcher',
      options: ['gala'],
      promo_code: 'etu',
    });
    expect(text(root)).toContain('60 000');
    page.orderForm.patchValue({ method: 'transfer' });
    await page.placeOrder();
    fixture.detectChanges();
    expect(service['order']).toHaveBeenCalledWith({
      category: 'researcher',
      options: ['gala'],
      promo_code: 'etu',
      method: 'transfer',
      billing_name: '',
      billing_organization: '',
      billing_address: '',
    });
    expect(redirect.go).not.toHaveBeenCalled();
    expect(text(root)).toContain('Commande enregistrée.');
    expect(text(root)).toContain('En attente de paiement');
    expect(text(root)).toContain('rappelez la référence');
  });

  it('options : celles de la catégorie seulement ; changement de catégorie = options vidées', async () => {
    const { fixture, root } = await render();
    const page = fixture.componentInstance as unknown as Page & {
      orderForm: { controls: { options: { value: string[] } } };
    };
    page.orderForm.patchValue({ category: 'student' });
    fixture.detectChanges();
    expect(text(root)).not.toContain('Dîner de gala');
    expect(text(root)).toContain('demande un justificatif');
    page.orderForm.patchValue({ category: 'researcher' });
    fixture.detectChanges();
    expect(text(root)).toContain('Dîner de gala');
    page.toggleOption('gala', true);
    page.categoryChanged();
    expect(page.orderForm.controls.options.value).toEqual([]);
  });

  it('commande en ligne : navigateur dirigé vers la page hébergée du prestataire', async () => {
    const { fixture } = await render();
    service['order'].mockResolvedValue(myRegistration({ method: 'online' }));
    const page = fixture.componentInstance as unknown as Page;
    page.orderForm.patchValue({ category: 'researcher', method: 'online' });
    await page.placeOrder();
    expect(service['pay']).toHaveBeenCalledWith(12);
    expect(redirect.go).toHaveBeenCalledWith('https://pay.test/p/1');
  });

  it('refus du serveur (quota atteint) : message du serveur affiché', async () => {
    const { fixture, root } = await render();
    service['order'].mockRejectedValue(
      new GcApiError(409, 'option_full', 'Plus de place pour « Dîner de gala ».', {
        options: ['Complet.'],
      }),
    );
    const page = fixture.componentInstance as unknown as Page;
    page.orderForm.patchValue({ category: 'researcher', method: 'transfer' });
    await page.placeOrder();
    fixture.detectChanges();
    expect(text(root)).toContain('Plus de place pour « Dîner de gala ».');
  });

  it('en attente : payer en ligne, pro forma, annulation confirmée', async () => {
    const { fixture, root } = await render([myRegistration()]);
    expect(root.querySelector('form')).toBeNull();
    button(root, 'Payer en ligne')!.click();
    await settle(fixture);
    expect(redirect.go).toHaveBeenCalledWith('https://pay.test/p/1');
    button(root, 'Obtenir une facture pro forma')!.click();
    await settle(fixture);
    expect(service['proforma']).toHaveBeenCalledWith(12);
    button(root, 'Annuler mon inscription')!.click();
    await settle(fixture);
    expect(service['cancel']).toHaveBeenCalledWith(12);
    expect(text(root)).toContain('Inscription annulée.');
  });

  it('RG-15 : au retour du paiement, le prestataire est interrogé, puis l’adresse nettoyée', async () => {
    const { root } = await render([myRegistration({ method: 'online' })], { paiement: 'P1' });
    expect(service['paymentCheck']).toHaveBeenCalledWith(12);
    expect(text(root)).toContain('Paiement reçu : votre inscription est confirmée.');
    expect(navigate).toHaveBeenCalledWith([], expect.objectContaining({ queryParams: {} }));
    // Confirmée : code d'accès et pièces par les endpoints authentifiés (règle n° 8).
    expect(root.querySelector('img.qr')!.getAttribute('src')).toBe('/api/v1/registrations/12/qr');
  });

  it('RG-15 : retour sans paiement confirmé = vérification en cours, jamais confirmée', async () => {
    check = { outcome: 'pending', status: 'pending' };
    const { root } = await render([myRegistration({ method: 'online' })], { paiement: 'P1' });
    expect(text(root)).toContain('Paiement en cours de vérification');
    expect(text(root)).toContain('En attente de paiement');
    expect(root.querySelector('img.qr')).toBeNull();
  });

  it('RG-15 : abandon sur la page du prestataire (échec) annoncé', async () => {
    check = { outcome: 'failed', status: 'pending' };
    const { root } = await render([myRegistration({ method: 'online' })], {
      paiement: 'P1',
      echec: '1',
    });
    expect(text(root)).toContain("Le paiement n'a pas abouti.");
  });

  it('confirmée : facture téléchargeable, annulation selon la date limite', async () => {
    const { root } = await render([
      myRegistration({
        status: 'confirmed',
        has_qr: true,
        can_cancel: false,
        cancellation_deadline: '2027-05-01T00:00:00Z',
        documents: [
          {
            id: 7,
            kind: 'invoice',
            number: 'F-GC27-2027-00001',
            amount: '50000.00',
            currency: 'XOF',
            issued_at: '2027-01-17T10:00:00Z',
          },
        ],
      }),
    ]);
    const link = root.querySelector<HTMLAnchorElement>('a[download]')!;
    expect(link.getAttribute('href')).toBe('/api/v1/registrations/12/documents/7');
    expect(link.textContent).toContain('F-GC27-2027-00001');
    expect(text(root)).toContain("La date limite d'annulation");
    expect(button(root, 'Annuler mon inscription')).toBeUndefined();
    expect(button(root, 'Payer en ligne')).toBeUndefined();
    // Facture émise : identité de facturation figée.
    expect(button(root, 'Modifier')).toBeUndefined();
  });

  it('aucune édition ouverte (404) : annonce, pas de formulaire', async () => {
    const { root } = await render([], {}, () =>
      Promise.reject(new GcApiError(404, 'not_found', 'Introuvable.')),
    );
    expect(text(root)).toContain('pas encore ouvertes');
    expect(root.querySelector('form')).toBeNull();
  });
});

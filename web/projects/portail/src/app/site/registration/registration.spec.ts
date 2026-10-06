import { TestBed } from '@angular/core/testing';
import { GcApiError } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { provideAccountTesting } from '../../account/testing';
import { RegistrationData } from './registration-data';
import { RegistrationOverview } from './registration-overview';
import { feeColumns, feeFor } from './registration-support';
import { CATALOG } from './testing';

function text(root: HTMLElement): string {
  return (root.textContent ?? '').replace(/[\u00a0\u202f]/g, ' ');
}

describe('Page publique « Inscription » (plan L6, J13)', () => {
  it('colonnes de la grille : couples proposés seulement, dans l’ordre période puis zone', () => {
    expect(feeColumns(CATALOG.categories)).toEqual([
      { period: 'early', zone: 'local' },
      { period: 'regular', zone: 'local' },
      { period: 'regular', zone: 'international' },
    ]);
    expect(feeFor(CATALOG.categories[1].fees, 'early', 'local')).toBeNull();
  });

  async function render(catalog: () => Promise<unknown>) {
    TestBed.configureTestingModule({
      providers: [
        ...provideAccountTesting(),
        { provide: RegistrationData, useValue: { catalog: vi.fn(catalog) } },
      ],
    });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(RegistrationOverview);
    fixture.componentRef.setInput('language', 'fr');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('grille, dates à l’heure de l’édition, options, moyens, lien vers « Mon inscription »', async () => {
    const root = await render(() => Promise.resolve(CATALOG));
    const content = text(root);
    expect(content).toContain('Tarifs en XOF');
    expect(content).toContain('Africa/Abidjan');
    expect(content).toContain('Fin du tarif préférentiel');
    const rows = Array.from(root.querySelectorAll('tbody tr')).map((tr) => text(tr as HTMLElement));
    expect(rows[0]).toContain('Chercheur');
    expect(rows[0]).toContain('40 000');
    expect(rows[0]).toContain('150 000');
    expect(rows[1]).toContain('justificatif demandé');
    expect(rows[1]).toContain('—');
    expect(content).toContain('Côte d’Ivoire');
    expect(content).toContain('Dîner de gala');
    expect(content).toContain('Places limitées.');
    expect(content).toContain('Réservée aux catégories : Chercheur.');
    expect(content).toContain('Virement (bon de commande, facture pro forma)');
    expect(root.querySelector('a[href="/compte/mon-inscription"]')!.textContent).toContain(
      "S'inscrire",
    );
    expect(root.querySelector('[role="region"][tabindex="0"]')).not.toBeNull();
  });

  it('sans édition ouverte (404) : inscriptions annoncées, sans erreur', async () => {
    const root = await render(() =>
      Promise.reject(new GcApiError(404, 'not_found', 'Introuvable.')),
    );
    expect(text(root)).toContain('Les inscriptions ne sont pas encore ouvertes');
    expect(root.querySelector('a[href="/compte/mon-inscription"]')).toBeNull();
  });
});

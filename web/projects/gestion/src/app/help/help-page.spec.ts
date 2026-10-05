import { TestBed } from '@angular/core/testing';
import { useTestLanguage } from '@gestconf/shared/testing';

import { provideGestionTesting } from '../../testing/gestion-testing';
import { HELP_SHEETS } from './help-sheets';
import { HelpPage } from './help-page';

describe('HelpPage', () => {
  async function render() {
    TestBed.configureTestingModule({ imports: [HelpPage], providers: provideGestionTesting() });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(HelpPage);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  it('sommaire, index par profil et par écran, toutes les fiches ancrées', async () => {
    const root = await render();
    expect(root.querySelector('h1')?.textContent).toContain('Guide de la gestion');
    expect(root.querySelectorAll('.toc a')).toHaveLength(HELP_SHEETS.length + 2);
    expect(root.querySelector('#index-profils h3')?.textContent).toContain(
      "Administrateur de l'édition",
    );
    expect(root.querySelectorAll('#index-ecrans > ul:first-of-type li')).toHaveLength(9);
    for (const sheet of HELP_SHEETS) {
      expect(root.querySelector(`#fiche-${sheet.id}`)).not.toBeNull();
    }
  });

  it('un clic dans le sommaire défile sans changer l’URL', async () => {
    const root = await render();
    const target = root.querySelector<HTMLElement>('#fiche-audit')!;
    target.scrollIntoView = vi.fn();
    const link = root.querySelector<HTMLAnchorElement>('.toc a[href="#fiche-audit"]')!;
    const event = new MouseEvent('click', { bubbles: true, cancelable: true });
    link.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(target.scrollIntoView).toHaveBeenCalled();
  });
});

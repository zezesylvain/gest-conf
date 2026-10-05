import { TestBed } from '@angular/core/testing';
import { MeEdition } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { CHAIR_EDITION, provideGestionTesting } from '../../testing/gestion-testing';
import { EditionLayout } from './edition-layout';

async function render(editions: MeEdition[], editionId = '3') {
  TestBed.configureTestingModule({
    imports: [EditionLayout],
    providers: provideGestionTesting(editions),
  });
  await useTestLanguage('fr');
  const fixture = TestBed.createComponent(EditionLayout);
  fixture.componentRef.setInput('editionId', editionId);
  await fixture.whenStable();
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

function links(root: HTMLElement): string[] {
  return Array.from(root.querySelectorAll('.edition-nav a')).map((a) => a.textContent!.trim());
}

describe('EditionLayout', () => {
  afterEach(() => localStorage.clear());

  it('menu complet pour un président de la conférence', async () => {
    const root = await render([CHAIR_EDITION]);
    expect(links(root)).toEqual([
      'Tableau de bord',
      'Informations générales',
      'Thématiques',
      'Types de communication',
      'Calendrier',
      'Confidentialité',
      'Membres',
      'Invitations',
      'Journal',
    ]);
  });

  it('président du CS : membres et invitations seulement', async () => {
    const root = await render([
      {
        ...CHAIR_EDITION,
        roles: [{ role: 'SC_CHAIR', oc_function: '' }],
        capabilities: ['members.read', 'members.manage'],
      },
    ]);
    expect(links(root)).toEqual(['Membres', 'Invitations']);
  });

  it('édition sans droit : message, aucun contenu', async () => {
    const root = await render([CHAIR_EDITION], '99');
    expect(links(root)).toEqual([]);
    expect(root.querySelector('[role=alert]')?.textContent).toContain('ne donnent pas accès');
  });
});

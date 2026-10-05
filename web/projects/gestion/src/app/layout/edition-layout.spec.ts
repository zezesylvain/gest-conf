import { ApplicationRef } from '@angular/core';
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

function links(root: HTMLElement, selector = '.rail a'): string[] {
  return Array.from(root.querySelectorAll(selector)).map((a) => a.textContent!.trim());
}

function openGroups(root: HTMLElement): string[] {
  return Array.from(root.querySelectorAll('.rail-toggle[aria-expanded=true]')).map((button) =>
    button.textContent!.trim(),
  );
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
      'Sections',
      'Pages',
      'Documents et images',
      'Menus',
      'Journal',
      'Guide',
    ]);
  });

  it('rail en accordéon : une seule catégorie ouverte, repli sur la première hors table', async () => {
    const root = await render([CHAIR_EDITION]);
    expect(openGroups(root)).toEqual(['Pilotage']);
    expect(links(root, '.rail ul:not([hidden]) a')).toEqual(['Tableau de bord']);
    expect(root.querySelectorAll('.rail ul[hidden]').length).toBe(5);
  });

  it('un clic ouvre une autre catégorie et referme la précédente', async () => {
    const root = await render([CHAIR_EDITION]);
    const settings = Array.from(root.querySelectorAll<HTMLButtonElement>('.rail-toggle')).find(
      (button) => button.textContent!.includes('Paramétrage'),
    )!;
    settings.click();
    await TestBed.inject(ApplicationRef).whenStable();
    expect(openGroups(root)).toEqual(['Paramétrage']);
    expect(settings.getAttribute('aria-controls')).toBe('rail-settings');
  });

  it('président du CS : membres et invitations seulement', async () => {
    const root = await render([
      {
        ...CHAIR_EDITION,
        roles: [{ role: 'SC_CHAIR', oc_function: '' }],
        capabilities: ['members.read', 'members.manage'],
      },
    ]);
    expect(links(root)).toEqual(['Membres', 'Invitations', 'Guide']);
  });

  it('édition sans droit : message, aucun contenu', async () => {
    const root = await render([CHAIR_EDITION], '99');
    expect(links(root)).toEqual([]);
    expect(root.querySelector('[role=alert]')?.textContent).toContain('ne donnent pas accès');
  });
});

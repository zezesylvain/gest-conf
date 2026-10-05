import { Type } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { MeEdition, MenuItem, Page, Section } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';
import { of } from 'rxjs';

import { CHAIR_EDITION, provideGestionTesting } from '../../../testing/gestion-testing';
import { moved, PortalApi } from '../../core/portal-api';
import { MenusPage } from './menus-page';
import { PageComposerPage } from './page-composer-page';
import { PortalStatusBanner } from './portal-status-banner';
import { SectionsPage } from './sections-page';

const PORTAL_CHAIR: MeEdition = {
  ...CHAIR_EDITION,
  capabilities: [...CHAIR_EDITION.capabilities, 'portal.write'],
};
const READER: MeEdition = {
  ...CHAIR_EDITION,
  roles: [{ role: 'OC_MEMBER', oc_function: 'finance' }],
  capabilities: ['edition.read'],
};

function section(id: number, code: string, pages: Section['pages'] = []): Section {
  return {
    id,
    code,
    section_type: 'rich_text',
    title_fr: code.toUpperCase(),
    published: true,
    is_data: false,
    image_ref: null,
    pages,
    updated_at: '2026-10-05T10:00:00Z',
  };
}

function page(sections: number[], isSystem = false): Page {
  return {
    id: 7,
    slug: isSystem ? 'home' : 'infos',
    is_system: isSystem,
    title_fr: 'Infos',
    published: true,
    paths: isSystem ? { fr: '/fr/', en: '/en/' } : { fr: '/fr/p/infos/', en: '/en/p/infos/' },
    sections: sections.map((id, position) => ({
      position,
      section: {
        id,
        code: `s${id}`,
        section_type: 'rich_text',
        title_fr: `S${id}`,
        title_en: '',
        published: true,
      },
    })),
    updated_at: '2026-10-05T10:00:00Z',
  };
}

let api: Record<string, ReturnType<typeof vi.fn>>;

async function setup(edition: MeEdition = PORTAL_CHAIR) {
  api = {
    status: vi.fn().mockResolvedValue({
      last_published_at: null,
      release: '',
      pending_changes: 3,
      pending_since: '2026-10-05T10:00:00Z',
    }),
    sections: vi.fn().mockResolvedValue([section(1, 'a'), section(2, 'b'), section(3, 'c')]),
    page: vi.fn().mockResolvedValue(page([1, 2])),
    reorder: vi.fn().mockResolvedValue(page([2, 1])),
    attach: vi.fn().mockResolvedValue(page([1, 2, 3])),
    detach: vi.fn().mockResolvedValue(page([2])),
    deleteSection: vi.fn().mockResolvedValue(undefined),
    pages: vi.fn().mockResolvedValue([page([], true), page([1])]),
    menu: vi.fn().mockResolvedValue([]),
    createMenuItem: vi.fn().mockResolvedValue({}),
    reorderMenu: vi.fn().mockResolvedValue([]),
  };
  TestBed.configureTestingModule({
    providers: [
      ...provideGestionTesting([edition]),
      { provide: PortalApi, useValue: api },
      { provide: MatDialog, useValue: { open: () => ({ afterClosed: () => of(true) }) } },
    ],
  });
  await useTestLanguage('fr');
}

async function render<T>(component: Type<T>, inputs: Record<string, string>) {
  const fixture = TestBed.createComponent(component);
  for (const [name, value] of Object.entries(inputs)) {
    fixture.componentRef.setInput(name, value);
  }
  await fixture.whenStable();
  fixture.detectChanges();
  await fixture.whenStable();
  return { fixture, root: fixture.nativeElement as HTMLElement };
}

function button(root: HTMLElement, text: string, index = 0): HTMLButtonElement {
  return Array.from(root.querySelectorAll<HTMLButtonElement>('button')).filter((b) =>
    b.textContent!.includes(text),
  )[index];
}

describe('moved', () => {
  it('échange avec le voisin, sans sortir des bornes', () => {
    expect(moved([1, 2, 3], 1, -1)).toEqual([2, 1, 3]);
    expect(moved([1, 2, 3], 1, 1)).toEqual([1, 3, 2]);
    expect(moved([1, 2, 3], 0, -1)).toEqual([1, 2, 3]);
    expect(moved([1, 2, 3], 2, 1)).toEqual([1, 2, 3]);
  });
});

describe('PageComposerPage', () => {
  it('« descendre » envoie la liste complète réordonnée et affiche la page relue', async () => {
    await setup();
    const { fixture, root } = await render(PageComposerPage, { editionId: '3', pageId: '7' });
    button(root, 'Descendre', 0).click();
    await fixture.whenStable();
    expect(api['reorder']).toHaveBeenCalledWith(3, 7, [2, 1]);
    fixture.detectChanges();
    const order = Array.from(root.querySelectorAll('.composition li a')).map((a) =>
      a.textContent!.trim(),
    );
    expect(order).toEqual(['S2', 'S1']);
  });

  it('seules les sections non posées sont proposées ; « monter » est désactivé en tête', async () => {
    await setup();
    const { fixture, root } = await render(PageComposerPage, { editionId: '3', pageId: '7' });
    const available = (fixture.componentInstance as unknown as { available: () => Section[] })
      .available()
      .map((item) => item.id);
    expect(available).toEqual([3]);
    expect(button(root, 'Monter', 0).disabled).toBe(true);
    expect(button(root, 'Descendre', 1).disabled).toBe(true);
  });

  it('retirer appelle detach', async () => {
    await setup();
    const { fixture, root } = await render(PageComposerPage, { editionId: '3', pageId: '7' });
    button(root, 'Retirer', 0).click();
    await fixture.whenStable();
    expect(api['detach']).toHaveBeenCalledWith(3, 7, 1);
  });

  it('page du site : gabarit annoncé, identifiant figé', async () => {
    await setup();
    api['page'].mockResolvedValue(page([1], true));
    const { root } = await render(PageComposerPage, { editionId: '3', pageId: '7' });
    expect(root.querySelector('.template')).not.toBeNull();
    expect(root.querySelector<HTMLInputElement>('input[formcontrolname=slug]')!.disabled).toBe(
      true,
    );
  });

  it('lecture seule sans portal.write : aucun bouton d’écriture', async () => {
    await setup(READER);
    const { root } = await render(PageComposerPage, { editionId: '3', pageId: '7' });
    expect(button(root, 'Descendre')).toBeUndefined();
    expect(button(root, 'Enregistrer')).toBeUndefined();
    expect(root.textContent).toContain('Lecture seule');
  });
});

describe('SectionsPage', () => {
  it('indique les pages qui portent chaque section ; suppression confirmée', async () => {
    await setup();
    api['sections'].mockResolvedValue([
      section(1, 'a', [{ id: 7, slug: 'home', title_fr: 'Accueil', is_system: true }]),
    ]);
    const { fixture, root } = await render(SectionsPage, { editionId: '3' });
    expect(root.querySelector('tbody tr td:nth-child(5)')?.textContent).toContain('Accueil');
    button(root, 'Supprimer').click();
    await fixture.whenStable();
    expect(api['deleteSection']).toHaveBeenCalledWith(3, 1);
  });

  it('lecture seule : pas de suppression ni de création', async () => {
    await setup(READER);
    const { root } = await render(SectionsPage, { editionId: '3' });
    expect(button(root, 'Supprimer')).toBeUndefined();
    expect(button(root, 'Ajouter une section')).toBeUndefined();
  });
});

describe('MenusPage', () => {
  it('une adresse : page nulle ; envoi au serveur', async () => {
    await setup();
    const { fixture, root } = await render(MenusPage, { editionId: '3' });
    expect(root.textContent).toContain('le portail affiche sa navigation par défaut');
    button(root, 'Ajouter une entrée', 1).click();
    await fixture.whenStable();
    const component = fixture.componentInstance as unknown as {
      form: { patchValue: (v: object) => void };
      save: () => Promise<void>;
    };
    component.form.patchValue({ label_fr: 'Contact', target: 'url', url: ' mailto:x@y.org ' });
    await component.save();
    expect(api['createMenuItem']).toHaveBeenCalledWith(3, {
      location: 'footer',
      label_fr: 'Contact',
      label_en: '',
      page: null,
      url: 'mailto:x@y.org',
      new_tab: false,
      published: true,
    });
  });

  it('« monter » envoie la liste complète de l’emplacement', async () => {
    await setup();
    const items: MenuItem[] = [1, 2].map((id) => ({
      id,
      location: 'header',
      label_fr: `E${id}`,
      page_ref: null,
      url: 'https://x.example',
      position: id,
      published: true,
    }));
    api['menu'].mockResolvedValue(items);
    const { fixture, root } = await render(MenusPage, { editionId: '3' });
    button(root, 'Monter', 1).click();
    await fixture.whenStable();
    expect(api['reorderMenu']).toHaveBeenCalledWith(3, 'header', [2, 1]);
  });
});

describe('PortalStatusBanner', () => {
  it('compte les modifications non publiées', async () => {
    await setup();
    const { root } = await render(PortalStatusBanner, { editionId: '3' });
    expect(root.textContent).toContain('3 modification(s) non publiée(s)');
    expect(root.textContent).toContain("n'a encore jamais été mis en ligne");
  });

  it('portail à jour', async () => {
    await setup();
    api['status'].mockResolvedValue({
      last_published_at: '2026-10-05T10:00:00Z',
      release: 'abc',
      pending_changes: 0,
      pending_since: null,
    });
    const { root } = await render(PortalStatusBanner, { editionId: '3' });
    expect(root.textContent).toContain('Le portail est à jour.');
    expect(root.textContent).toContain('Dernière mise en ligne');
  });
});

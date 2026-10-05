import { inject, Injectable } from '@angular/core';
import {
  Api,
  manageEditionsPortalMenuCreate,
  manageEditionsPortalMenuDestroy,
  manageEditionsPortalMenuList,
  manageEditionsPortalMenuPartialUpdate,
  manageEditionsPortalPagesCreate,
  manageEditionsPortalPagesDestroy,
  manageEditionsPortalPagesList,
  manageEditionsPortalPagesPartialUpdate,
  manageEditionsPortalPagesRetrieve,
  manageEditionsPortalSectionsCreate,
  manageEditionsPortalSectionsDestroy,
  manageEditionsPortalSectionsList,
  manageEditionsPortalSectionsPartialUpdate,
  manageEditionsPortalSectionsRetrieve,
  manageEditionsPortalFilesCreate,
  manageEditionsPortalFilesDestroy,
  manageEditionsPortalFilesList,
  manageEditionsPortalFilesPartialUpdate$Json,
  managePortalMenuReorder,
  managePortalPoster,
  managePortalPosterUpdate,
  managePortalPagesAttach,
  managePortalPagesDetach,
  managePortalPagesReorder,
  managePortalSectionsPreview,
  managePortalStatus,
  MenuItem,
  MenuItemRequest,
  MenuLocation,
  Page,
  PageRequest,
  PatchedMenuItemRequest,
  PatchedPageRequest,
  PatchedPublicFileRequest,
  PortalFileKind,
  Poster,
  PublicFile,
  PatchedSectionWriteRequest,
  Preview,
  PublicationStatus,
  Section,
  SectionWriteRequest,
} from '@gestconf/shared';

/**
 * Contenus du portail (plan L2 §4), par le client généré. Lecture : `edition.read` ;
 * écriture : `portal.write`. Le serveur décide (règle n° 2).
 */
@Injectable({ providedIn: 'root' })
export class PortalApi {
  private readonly api = inject(Api);

  status(editionId: number): Promise<PublicationStatus> {
    return this.api.invoke(managePortalStatus, { edition_id: editionId });
  }

  sections(editionId: number): Promise<Section[]> {
    return this.api.invoke(manageEditionsPortalSectionsList, { edition_id: editionId });
  }

  section(editionId: number, id: number): Promise<Section> {
    return this.api.invoke(manageEditionsPortalSectionsRetrieve, {
      edition_id: editionId,
      item_id: id,
    });
  }

  createSection(editionId: number, body: SectionWriteRequest): Promise<Section> {
    return this.api.invoke(manageEditionsPortalSectionsCreate, { edition_id: editionId, body });
  }

  updateSection(editionId: number, id: number, body: PatchedSectionWriteRequest): Promise<Section> {
    return this.api.invoke(manageEditionsPortalSectionsPartialUpdate, {
      edition_id: editionId,
      item_id: id,
      body,
    });
  }

  deleteSection(editionId: number, id: number): Promise<void> {
    return this.api.invoke(manageEditionsPortalSectionsDestroy, {
      edition_id: editionId,
      item_id: id,
    });
  }

  preview(editionId: number, bodyFr: string, bodyEn: string): Promise<Preview> {
    return this.api.invoke(managePortalSectionsPreview, {
      edition_id: editionId,
      body: { body_fr: bodyFr, body_en: bodyEn },
    });
  }

  pages(editionId: number): Promise<Page[]> {
    return this.api.invoke(manageEditionsPortalPagesList, { edition_id: editionId });
  }

  page(editionId: number, id: number): Promise<Page> {
    return this.api.invoke(manageEditionsPortalPagesRetrieve, {
      edition_id: editionId,
      item_id: id,
    });
  }

  createPage(editionId: number, body: PageRequest): Promise<Page> {
    return this.api.invoke(manageEditionsPortalPagesCreate, { edition_id: editionId, body });
  }

  updatePage(editionId: number, id: number, body: PatchedPageRequest): Promise<Page> {
    return this.api.invoke(manageEditionsPortalPagesPartialUpdate, {
      edition_id: editionId,
      item_id: id,
      body,
    });
  }

  deletePage(editionId: number, id: number): Promise<void> {
    return this.api.invoke(manageEditionsPortalPagesDestroy, {
      edition_id: editionId,
      item_id: id,
    });
  }

  /** Pose une section (à la fin, ou à `position`) ; renvoie la page relue. */
  attach(editionId: number, pageId: number, section: number, position?: number): Promise<Page> {
    return this.api.invoke(managePortalPagesAttach, {
      edition_id: editionId,
      item_id: pageId,
      body: position === undefined ? { section } : { section, position },
    });
  }

  detach(editionId: number, pageId: number, section: number): Promise<Page> {
    return this.api.invoke(managePortalPagesDetach, {
      edition_id: editionId,
      item_id: pageId,
      body: { section },
    });
  }

  /** Ordre en **liste complète** des sections posées. */
  reorder(editionId: number, pageId: number, sections: number[]): Promise<Page> {
    return this.api.invoke(managePortalPagesReorder, {
      edition_id: editionId,
      item_id: pageId,
      body: { sections },
    });
  }

  menu(editionId: number): Promise<MenuItem[]> {
    return this.api.invoke(manageEditionsPortalMenuList, { edition_id: editionId });
  }

  createMenuItem(editionId: number, body: MenuItemRequest): Promise<MenuItem> {
    return this.api.invoke(manageEditionsPortalMenuCreate, { edition_id: editionId, body });
  }

  updateMenuItem(editionId: number, id: number, body: PatchedMenuItemRequest): Promise<MenuItem> {
    return this.api.invoke(manageEditionsPortalMenuPartialUpdate, {
      edition_id: editionId,
      item_id: id,
      body,
    });
  }

  deleteMenuItem(editionId: number, id: number): Promise<void> {
    return this.api.invoke(manageEditionsPortalMenuDestroy, {
      edition_id: editionId,
      item_id: id,
    });
  }

  /** Ordre en **liste complète** des entrées d'un emplacement ; renvoie la liste relue. */
  reorderMenu(editionId: number, location: MenuLocation, items: number[]): Promise<MenuItem[]> {
    return this.api.invoke(managePortalMenuReorder, {
      edition_id: editionId,
      body: { location, items },
    });
  }
}

/** Fichiers publics de l'édition (L2.4) : documents et images, affiche. */
@Injectable({ providedIn: 'root' })
export class PortalFilesApi {
  private readonly api = inject(Api);

  files(editionId: number, kind?: PortalFileKind): Promise<PublicFile[]> {
    return this.api.invoke(manageEditionsPortalFilesList, {
      edition_id: editionId,
      ...(kind ? { kind } : {}),
    });
  }

  /** Téléversement (multipart) : le serveur vérifie le type par le contenu. */
  upload(
    editionId: number,
    file: File,
    kind: PortalFileKind,
    titleFr = '',
    titleEn = '',
  ): Promise<PublicFile> {
    return this.api.invoke(manageEditionsPortalFilesCreate, {
      edition_id: editionId,
      body: { file, kind, title_fr: titleFr, title_en: titleEn },
    });
  }

  update(editionId: number, id: number, body: PatchedPublicFileRequest): Promise<PublicFile> {
    return this.api.invoke(manageEditionsPortalFilesPartialUpdate$Json, {
      edition_id: editionId,
      item_id: id,
      body,
    });
  }

  remove(editionId: number, id: number): Promise<void> {
    return this.api.invoke(manageEditionsPortalFilesDestroy, {
      edition_id: editionId,
      item_id: id,
    });
  }

  poster(editionId: number): Promise<Poster> {
    return this.api.invoke(managePortalPoster, { edition_id: editionId });
  }

  setPoster(editionId: number, file: number | null): Promise<Poster> {
    return this.api.invoke(managePortalPosterUpdate, { edition_id: editionId, body: { file } });
  }
}

/** Déplace l'élément d'index `index` de `delta` (−1 : monter, +1 : descendre). */
export function moved<T>(items: readonly T[], index: number, delta: -1 | 1): T[] {
  const target = index + delta;
  if (target < 0 || target >= items.length) {
    return [...items];
  }
  const result = [...items];
  [result[index], result[target]] = [result[target], result[index]];
  return result;
}

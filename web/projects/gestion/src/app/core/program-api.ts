import { inject, Injectable } from '@angular/core';
import {
  Api,
  GcApiError,
  manageProgramBoard,
  manageProgramPeople,
  manageProgramPublications,
  manageProgramPublish,
  manageProgramRolesCreate,
  manageProgramRolesDelete,
  manageProgramRoomsCreate,
  manageProgramRoomsDelete,
  manageProgramRoomsUpdate,
  manageProgramSessionsCreate,
  manageProgramSessionsDelete,
  manageProgramSessionsUpdate,
  manageProgramSettingsRetrieve,
  manageProgramSettingsUpdate,
  manageProgramSlotsCreate,
  manageProgramSlotsDelete,
  manageProgramSlotsUpdate,
  PatchedProgramSettingsRequest,
  PatchedRoomWriteRequest,
  PatchedSessionWriteRequest,
  PatchedSlotUpdateRequest,
  PersonSearch,
  ProgramBoard,
  ProgramSettings,
  Publication,
  RoomWriteRequest,
  SessionRoleWriteRequest,
  SessionWriteRequest,
  SlotCreateRequest,
} from '@gestconf/shared';

/**
 * Programme dans la gestion (client généré, plan L5 §4). Lecture `program.read`, écriture
 * `program.write`, publication `program.publish` (Chair, réauthentification récente).
 *
 * Chaque écriture porte la révision lue (`If-Match`, I14) et renvoie le **brouillon complet**,
 * conflits compris (RG-12, RG-13) : l'écran remplace son état par la réponse. Le serveur
 * vérifie chaque appel (règle n° 2).
 */
@Injectable({ providedIn: 'root' })
export class ProgramApi {
  private readonly api = inject(Api);

  board(editionId: number): Promise<ProgramBoard> {
    return this.api.invoke(manageProgramBoard, { edition_id: editionId });
  }

  settings(editionId: number): Promise<ProgramSettings> {
    return this.api.invoke(manageProgramSettingsRetrieve, { edition_id: editionId });
  }

  updateSettings(editionId: number, body: PatchedProgramSettingsRequest): Promise<ProgramSettings> {
    return this.api.invoke(manageProgramSettingsUpdate, { edition_id: editionId, body });
  }

  // --- Salles (I9) ---------------------------------------------------------------------------

  createRoom(editionId: number, revision: number, body: RoomWriteRequest): Promise<ProgramBoard> {
    return this.api.invoke(manageProgramRoomsCreate, {
      edition_id: editionId,
      'If-Match': revision,
      body,
    });
  }

  updateRoom(
    editionId: number,
    revision: number,
    roomId: number,
    body: PatchedRoomWriteRequest,
  ): Promise<ProgramBoard> {
    return this.api.invoke(manageProgramRoomsUpdate, {
      edition_id: editionId,
      item_id: roomId,
      'If-Match': revision,
      body,
    });
  }

  deleteRoom(editionId: number, revision: number, roomId: number): Promise<ProgramBoard> {
    return this.api.invoke(manageProgramRoomsDelete, {
      edition_id: editionId,
      item_id: roomId,
      'If-Match': revision,
    });
  }

  // --- Sessions (I2, I12) --------------------------------------------------------------------

  createSession(
    editionId: number,
    revision: number,
    body: SessionWriteRequest,
  ): Promise<ProgramBoard> {
    return this.api.invoke(manageProgramSessionsCreate, {
      edition_id: editionId,
      'If-Match': revision,
      body,
    });
  }

  updateSession(
    editionId: number,
    revision: number,
    sessionId: number,
    body: PatchedSessionWriteRequest,
  ): Promise<ProgramBoard> {
    return this.api.invoke(manageProgramSessionsUpdate, {
      edition_id: editionId,
      item_id: sessionId,
      'If-Match': revision,
      body,
    });
  }

  deleteSession(editionId: number, revision: number, sessionId: number): Promise<ProgramBoard> {
    return this.api.invoke(manageProgramSessionsDelete, {
      edition_id: editionId,
      item_id: sessionId,
      'If-Match': revision,
    });
  }

  // --- Créneaux (I3) -------------------------------------------------------------------------

  createSlot(
    editionId: number,
    revision: number,
    sessionId: number,
    body: SlotCreateRequest,
  ): Promise<ProgramBoard> {
    return this.api.invoke(manageProgramSlotsCreate, {
      edition_id: editionId,
      session_id: sessionId,
      'If-Match': revision,
      body,
    });
  }

  updateSlot(
    editionId: number,
    revision: number,
    slotId: number,
    body: PatchedSlotUpdateRequest,
  ): Promise<ProgramBoard> {
    return this.api.invoke(manageProgramSlotsUpdate, {
      edition_id: editionId,
      item_id: slotId,
      'If-Match': revision,
      body,
    });
  }

  deleteSlot(editionId: number, revision: number, slotId: number): Promise<ProgramBoard> {
    return this.api.invoke(manageProgramSlotsDelete, {
      edition_id: editionId,
      item_id: slotId,
      'If-Match': revision,
    });
  }

  // --- Rôles de séance (I10) -----------------------------------------------------------------

  addRole(
    editionId: number,
    revision: number,
    sessionId: number,
    body: SessionRoleWriteRequest,
  ): Promise<ProgramBoard> {
    return this.api.invoke(manageProgramRolesCreate, {
      edition_id: editionId,
      session_id: sessionId,
      'If-Match': revision,
      body,
    });
  }

  removeRole(editionId: number, revision: number, roleId: number): Promise<ProgramBoard> {
    return this.api.invoke(manageProgramRolesDelete, {
      edition_id: editionId,
      item_id: roleId,
      'If-Match': revision,
    });
  }

  /** Personnes de l'édition (nom, institution, rôles ; jamais d'adresse), 20 au plus. */
  people(editionId: number, q: string): Promise<PersonSearch[]> {
    return this.api.invoke(manageProgramPeople, { edition_id: editionId, q });
  }

  // --- Publication (I6, I13) -----------------------------------------------------------------

  publish(editionId: number, revision: number): Promise<ProgramBoard> {
    return this.api.invoke(manageProgramPublish, { edition_id: editionId, 'If-Match': revision });
  }

  /** Historique des publications, de la plus récente à la plus ancienne. */
  publications(editionId: number): Promise<Publication[]> {
    return this.api.invoke(manageProgramPublications, { edition_id: editionId });
  }
}

/** Révision périmée (412, I14) : un autre membre a modifié le programme entre-temps. */
export function isStaleRevision(error: unknown): boolean {
  return error instanceof GcApiError && error.status === 412;
}

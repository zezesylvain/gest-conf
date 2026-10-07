import { inject, Injectable } from '@angular/core';
import {
  Api,
  DietarySummary,
  ManageVisit,
  Meal,
  MealWriteRequest,
  PatchedMealWriteRequest,
  PatchedShiftWriteRequest,
  PatchedVisitStaffWriteRequest,
  Shift,
  ShiftBoard,
  ShiftWriteRequest,
  manageDietaryExport,
  manageDietarySummary,
  manageMealsCreate,
  manageMealsDestroy,
  manageMealsExport,
  manageMealsList,
  manageMealsUpdate,
  manageMyShifts,
  manageMyShiftsCalendar,
  manageShiftsAssign,
  manageShiftsCreate,
  manageShiftsDestroy,
  manageShiftsList,
  manageShiftsUnassign,
  manageShiftsUpdate,
  manageVisitsList,
  manageVisitsRetrieve,
  manageVisitsUpdate,
} from '@gestconf/shared';

/**
 * Logistique dans la gestion (plan L8, N6 à N9 ; client généré) : venues des intervenants
 * invités et régimes (`logistics.read`, écriture `logistics.write`), restauration, postes de
 * bénévoles (`volunteers.plan`) et « Mon planning » du bénévole (`shifts.own`). Tout est
 * revérifié par le serveur (règle n° 2) ; la liste nominative des régimes (RG-23) demande une
 * réauthentification récente, que l'intercepteur ouvre avant de rejouer la requête.
 */
@Injectable({ providedIn: 'root' })
export class LogisticsApi {
  private readonly api = inject(Api);

  // --- Venues des intervenants invités (N6) ------------------------------------------------

  visits(editionId: number): Promise<ManageVisit[]> {
    return this.api.invoke(manageVisitsList, { edition_id: editionId });
  }

  visit(editionId: number, userId: number): Promise<ManageVisit> {
    return this.api.invoke(manageVisitsRetrieve, { edition_id: editionId, user_id: userId });
  }

  updateVisit(
    editionId: number,
    userId: number,
    body: PatchedVisitStaffWriteRequest,
  ): Promise<ManageVisit> {
    return this.api.invoke(manageVisitsUpdate, { edition_id: editionId, user_id: userId, body });
  }

  // --- Régimes (N7, RG-23) et repas (N8) -----------------------------------------------------

  dietary(editionId: number): Promise<DietarySummary> {
    return this.api.invoke(manageDietarySummary, { edition_id: editionId });
  }

  exportDietary(editionId: number, fileFormat: 'csv' | 'xlsx'): Promise<Blob> {
    return this.api.invoke(manageDietaryExport, { edition_id: editionId, file_format: fileFormat });
  }

  meals(editionId: number): Promise<Meal[]> {
    return this.api.invoke(manageMealsList, { edition_id: editionId });
  }

  createMeal(editionId: number, body: MealWriteRequest): Promise<Meal[]> {
    return this.api.invoke(manageMealsCreate, { edition_id: editionId, body });
  }

  updateMeal(editionId: number, mealId: number, body: PatchedMealWriteRequest): Promise<Meal[]> {
    return this.api.invoke(manageMealsUpdate, { edition_id: editionId, meal_id: mealId, body });
  }

  deleteMeal(editionId: number, mealId: number): Promise<Meal[]> {
    return this.api.invoke(manageMealsDestroy, { edition_id: editionId, meal_id: mealId });
  }

  exportMeals(editionId: number, fileFormat: 'csv' | 'xlsx' | 'pdf'): Promise<Blob> {
    return this.api.invoke(manageMealsExport, { edition_id: editionId, file_format: fileFormat });
  }

  // --- Bénévoles (N9) -------------------------------------------------------------------------

  shifts(editionId: number): Promise<ShiftBoard> {
    return this.api.invoke(manageShiftsList, { edition_id: editionId });
  }

  createShift(editionId: number, body: ShiftWriteRequest): Promise<ShiftBoard> {
    return this.api.invoke(manageShiftsCreate, { edition_id: editionId, body });
  }

  updateShift(
    editionId: number,
    shiftId: number,
    body: PatchedShiftWriteRequest,
  ): Promise<ShiftBoard> {
    return this.api.invoke(manageShiftsUpdate, { edition_id: editionId, shift_id: shiftId, body });
  }

  deleteShift(editionId: number, shiftId: number): Promise<ShiftBoard> {
    return this.api.invoke(manageShiftsDestroy, { edition_id: editionId, shift_id: shiftId });
  }

  assign(editionId: number, shiftId: number, volunteerId: number): Promise<ShiftBoard> {
    return this.api.invoke(manageShiftsAssign, {
      edition_id: editionId,
      shift_id: shiftId,
      body: { volunteer: volunteerId },
    });
  }

  unassign(editionId: number, shiftId: number, volunteerId: number): Promise<ShiftBoard> {
    return this.api.invoke(manageShiftsUnassign, {
      edition_id: editionId,
      shift_id: shiftId,
      volunteer_id: volunteerId,
    });
  }

  myShifts(editionId: number): Promise<Shift[]> {
    return this.api.invoke(manageMyShifts, { edition_id: editionId });
  }

  myCalendar(editionId: number): Promise<Blob> {
    return this.api.invoke(manageMyShiftsCalendar, { edition_id: editionId });
  }
}

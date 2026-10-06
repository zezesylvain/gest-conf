import { inject, Injectable } from '@angular/core';
import {
  Api,
  BillingProfile,
  CancelRequest,
  Category,
  CategoryRequest,
  FeeRequest,
  FinanceDashboard,
  ManageOrderRequest,
  ManageRegistration,
  ManualPaymentRequest,
  manageBillingDashboard,
  manageBillingDocumentsExport,
  manageBillingDocumentsList,
  ManageBillingDocumentsList$Params,
  manageBillingIssuePending,
  manageBillingPaymentsExport,
  manageBillingPaymentsList,
  ManageBillingPaymentsList$Params,
  manageBillingProfileRetrieve,
  manageBillingProfileUpdate,
  manageRegistrationCategoriesCreate,
  manageRegistrationCategoriesDelete,
  manageRegistrationCategoriesFees,
  manageRegistrationCategoriesList,
  manageRegistrationCategoriesUpdate,
  manageRegistrationOptionsCreate,
  manageRegistrationOptionsDelete,
  manageRegistrationOptionsList,
  manageRegistrationOptionsUpdate,
  manageRegistrationPromoCodesCreate,
  manageRegistrationPromoCodesDelete,
  manageRegistrationPromoCodesList,
  manageRegistrationPromoCodesUpdate,
  manageRegistrationsCancel,
  manageRegistrationsCreate,
  manageRegistrationSettingsRetrieve,
  manageRegistrationSettingsUpdate,
  manageRegistrationsExport,
  manageRegistrationsList,
  ManageRegistrationsList$Params,
  manageRegistrationsPayment,
  manageRegistrationsProforma,
  manageRegistrationsRefund,
  manageRegistrationsRetrieve,
  manageRegistrationsWaive,
  Option,
  OptionRequest,
  PaginatedBillingDocumentList,
  PaginatedManageRegistrationListList,
  PaginatedPaymentListList,
  PatchedBillingProfileRequest,
  PatchedCategoryRequest,
  PatchedOptionRequest,
  PatchedPromoCodeRequest,
  PatchedRegistrationSettingsRequest,
  PromoCode,
  PromoCodeRequest,
  RefundRequest,
  RegistrationSettings,
  WaiverRequest,
} from '@gestconf/shared';

/** Filtres de la liste des inscriptions et de son export (mêmes paramètres). */
export type RegistrationFilters = Omit<ManageRegistrationsList$Params, 'edition_id'>;
export type PaymentFilters = Omit<ManageBillingPaymentsList$Params, 'edition_id'>;
export type DocumentFilters = Omit<ManageBillingDocumentsList$Params, 'edition_id'>;

/**
 * Inscriptions, tarifs et finances d'une édition dans la gestion (plan L6, J12 ; client
 * généré). Lecture `registrations.read`, gestion `registrations.manage`, tarifs
 * `pricing.write`, finances `finance.read` : vérifiés par le serveur à chaque appel
 * (règle n° 2). Paiement manuel, remboursement, exports et mentions de facturation
 * demandent une réauthentification récente : l'intercepteur ouvre la fenêtre et rejoue.
 */
@Injectable({ providedIn: 'root' })
export class RegistrationsApi {
  private readonly api = inject(Api);

  // --- Paramètres et mentions -------------------------------------------------------------

  settings(editionId: number): Promise<RegistrationSettings> {
    return this.api.invoke(manageRegistrationSettingsRetrieve, { edition_id: editionId });
  }

  updateSettings(
    editionId: number,
    body: PatchedRegistrationSettingsRequest,
  ): Promise<RegistrationSettings> {
    return this.api.invoke(manageRegistrationSettingsUpdate, { edition_id: editionId, body });
  }

  billingProfile(editionId: number): Promise<BillingProfile> {
    return this.api.invoke(manageBillingProfileRetrieve, { edition_id: editionId });
  }

  updateBillingProfile(
    editionId: number,
    body: PatchedBillingProfileRequest,
  ): Promise<BillingProfile> {
    return this.api.invoke(manageBillingProfileUpdate, { edition_id: editionId, body });
  }

  // --- Catalogue ----------------------------------------------------------------------------

  categories(editionId: number): Promise<Category[]> {
    return this.api.invoke(manageRegistrationCategoriesList, { edition_id: editionId });
  }

  createCategory(editionId: number, body: CategoryRequest): Promise<Category> {
    return this.api.invoke(manageRegistrationCategoriesCreate, { edition_id: editionId, body });
  }

  updateCategory(editionId: number, id: number, body: PatchedCategoryRequest): Promise<Category> {
    return this.api.invoke(manageRegistrationCategoriesUpdate, {
      edition_id: editionId,
      item_id: id,
      body,
    });
  }

  deleteCategory(editionId: number, id: number): Promise<void> {
    return this.api.invoke(manageRegistrationCategoriesDelete, {
      edition_id: editionId,
      item_id: id,
    });
  }

  setFees(editionId: number, id: number, fees: FeeRequest[]): Promise<Category> {
    return this.api.invoke(manageRegistrationCategoriesFees, {
      edition_id: editionId,
      item_id: id,
      body: { fees },
    });
  }

  options(editionId: number): Promise<Option[]> {
    return this.api.invoke(manageRegistrationOptionsList, { edition_id: editionId });
  }

  createOption(editionId: number, body: OptionRequest): Promise<Option> {
    return this.api.invoke(manageRegistrationOptionsCreate, { edition_id: editionId, body });
  }

  updateOption(editionId: number, id: number, body: PatchedOptionRequest): Promise<Option> {
    return this.api.invoke(manageRegistrationOptionsUpdate, {
      edition_id: editionId,
      item_id: id,
      body,
    });
  }

  deleteOption(editionId: number, id: number): Promise<void> {
    return this.api.invoke(manageRegistrationOptionsDelete, {
      edition_id: editionId,
      item_id: id,
    });
  }

  promoCodes(editionId: number): Promise<PromoCode[]> {
    return this.api.invoke(manageRegistrationPromoCodesList, { edition_id: editionId });
  }

  createPromoCode(editionId: number, body: PromoCodeRequest): Promise<PromoCode> {
    return this.api.invoke(manageRegistrationPromoCodesCreate, { edition_id: editionId, body });
  }

  updatePromoCode(
    editionId: number,
    id: number,
    body: PatchedPromoCodeRequest,
  ): Promise<PromoCode> {
    return this.api.invoke(manageRegistrationPromoCodesUpdate, {
      edition_id: editionId,
      item_id: id,
      body,
    });
  }

  deletePromoCode(editionId: number, id: number): Promise<void> {
    return this.api.invoke(manageRegistrationPromoCodesDelete, {
      edition_id: editionId,
      item_id: id,
    });
  }

  // --- Inscriptions -------------------------------------------------------------------------

  list(
    editionId: number,
    filters: RegistrationFilters,
  ): Promise<PaginatedManageRegistrationListList> {
    return this.api.invoke(manageRegistrationsList, { edition_id: editionId, ...filters });
  }

  get(editionId: number, id: number): Promise<ManageRegistration> {
    return this.api.invoke(manageRegistrationsRetrieve, { edition_id: editionId, item_id: id });
  }

  create(editionId: number, body: ManageOrderRequest): Promise<ManageRegistration> {
    return this.api.invoke(manageRegistrationsCreate, { edition_id: editionId, body });
  }

  cancel(editionId: number, id: number, body: CancelRequest): Promise<ManageRegistration> {
    return this.api.invoke(manageRegistrationsCancel, {
      edition_id: editionId,
      item_id: id,
      body,
    });
  }

  waive(editionId: number, id: number, body: WaiverRequest): Promise<ManageRegistration> {
    return this.api.invoke(manageRegistrationsWaive, { edition_id: editionId, item_id: id, body });
  }

  recordPayment(
    editionId: number,
    id: number,
    body: ManualPaymentRequest,
  ): Promise<ManageRegistration> {
    return this.api.invoke(manageRegistrationsPayment, {
      edition_id: editionId,
      item_id: id,
      body,
    });
  }

  recordRefund(editionId: number, id: number, body: RefundRequest): Promise<ManageRegistration> {
    return this.api.invoke(manageRegistrationsRefund, {
      edition_id: editionId,
      item_id: id,
      body,
    });
  }

  issueProforma(editionId: number, id: number): Promise<ManageRegistration> {
    return this.api.invoke(manageRegistrationsProforma, { edition_id: editionId, item_id: id });
  }

  exportRegistrations(editionId: number, filters: RegistrationFilters): Promise<Blob> {
    return this.api.invoke(manageRegistrationsExport, { edition_id: editionId, ...filters });
  }

  // --- Finances -------------------------------------------------------------------------------

  payments(editionId: number, filters: PaymentFilters): Promise<PaginatedPaymentListList> {
    return this.api.invoke(manageBillingPaymentsList, { edition_id: editionId, ...filters });
  }

  exportPayments(editionId: number, filters: PaymentFilters): Promise<Blob> {
    return this.api.invoke(manageBillingPaymentsExport, { edition_id: editionId, ...filters });
  }

  documents(editionId: number, filters: DocumentFilters): Promise<PaginatedBillingDocumentList> {
    return this.api.invoke(manageBillingDocumentsList, { edition_id: editionId, ...filters });
  }

  exportDocuments(editionId: number, kind?: string): Promise<Blob> {
    return this.api.invoke(manageBillingDocumentsExport, { edition_id: editionId, kind });
  }

  issuePendingInvoices(editionId: number): Promise<{ issued: number }> {
    return this.api.invoke(manageBillingIssuePending, { edition_id: editionId });
  }

  dashboard(editionId: number): Promise<FinanceDashboard> {
    return this.api.invoke(manageBillingDashboard, { edition_id: editionId });
  }
}

/** PDF d'une pièce de l'inscription, ou justificatif (endpoints authentifiés, règle n° 8). */
export function documentUrl(
  editionId: number | string,
  registrationId: number,
  documentId: number,
): string {
  return `/api/v1/manage/editions/${editionId}/registrations/${registrationId}/documents/${documentId}`;
}

export function proofUrl(editionId: number | string, registrationId: number): string {
  return `/api/v1/manage/editions/${editionId}/registrations/${registrationId}/proof`;
}

/** Enregistre un fichier reçu (export CSV) sans quitter la page. */
export function saveBlob(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
}

/** Montant décimal (« 25000.00 ») au format de la langue et de la devise (Intl). */
export function money(amount: string | number | null | undefined, currency: string, lang: string) {
  if (amount === null || amount === undefined || amount === '') {
    return '—';
  }
  return new Intl.NumberFormat(lang === 'en' ? 'en-GB' : 'fr-FR', {
    style: 'currency',
    currency,
  }).format(Number(amount));
}

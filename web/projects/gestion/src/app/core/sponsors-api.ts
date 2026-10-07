import { inject, Injectable } from '@angular/core';
import {
  Api,
  PatchedSponsorLevelWriteRequest,
  PatchedSponsorWriteRequest,
  SponsorDetail,
  SponsorLevel,
  SponsorLevelWriteRequest,
  Sponsors,
  SponsorWriteRequest,
  manageSponsorLevelsCreate,
  manageSponsorLevelsDestroy,
  manageSponsorLevelsList,
  manageSponsorLevelsUpdate,
  manageSponsorsBenefitsAdd,
  manageSponsorsBenefitsRemove,
  manageSponsorsBenefitsUpdate,
  manageSponsorsCreate,
  manageSponsorsDestroy,
  manageSponsorsExport,
  manageSponsorsList,
  manageSponsorsLogoRemove,
  manageSponsorsLogoUpload,
  manageSponsorsRetrieve,
  manageSponsorsUpdate,
} from '@gestconf/shared';

/**
 * Partenaires dans la gestion (plan L8, N5 ; client généré) : lecture `sponsors.read`,
 * écriture `sponsors.write`, revérifiées par le serveur (règle n° 2). L'export contient les
 * contacts : réauthentification récente, que l'intercepteur ouvre avant de rejouer la
 * requête, et journal.
 */
@Injectable({ providedIn: 'root' })
export class SponsorsApi {
  private readonly api = inject(Api);

  sponsors(editionId: number): Promise<Sponsors> {
    return this.api.invoke(manageSponsorsList, { edition_id: editionId });
  }

  sponsor(editionId: number, sponsorId: number): Promise<SponsorDetail> {
    return this.api.invoke(manageSponsorsRetrieve, {
      edition_id: editionId,
      sponsor_id: sponsorId,
    });
  }

  create(editionId: number, body: SponsorWriteRequest): Promise<SponsorDetail> {
    return this.api.invoke(manageSponsorsCreate, { edition_id: editionId, body });
  }

  update(
    editionId: number,
    sponsorId: number,
    body: PatchedSponsorWriteRequest,
  ): Promise<SponsorDetail> {
    return this.api.invoke(manageSponsorsUpdate, {
      edition_id: editionId,
      sponsor_id: sponsorId,
      body,
    });
  }

  remove(editionId: number, sponsorId: number): Promise<void> {
    return this.api.invoke(manageSponsorsDestroy, { edition_id: editionId, sponsor_id: sponsorId });
  }

  exportSponsors(editionId: number, fileFormat: 'csv' | 'xlsx'): Promise<Blob> {
    return this.api.invoke(manageSponsorsExport, {
      edition_id: editionId,
      file_format: fileFormat,
    });
  }

  uploadLogo(editionId: number, sponsorId: number, file: Blob): Promise<SponsorDetail> {
    return this.api.invoke(manageSponsorsLogoUpload, {
      edition_id: editionId,
      sponsor_id: sponsorId,
      body: { file },
    });
  }

  removeLogo(editionId: number, sponsorId: number): Promise<SponsorDetail> {
    return this.api.invoke(manageSponsorsLogoRemove, {
      edition_id: editionId,
      sponsor_id: sponsorId,
    });
  }

  addBenefit(editionId: number, sponsorId: number, label: string): Promise<SponsorDetail> {
    return this.api.invoke(manageSponsorsBenefitsAdd, {
      edition_id: editionId,
      sponsor_id: sponsorId,
      body: { label },
    });
  }

  markBenefit(
    editionId: number,
    sponsorId: number,
    benefitId: number,
    deliveredOn: string | null,
  ): Promise<SponsorDetail> {
    return this.api.invoke(manageSponsorsBenefitsUpdate, {
      edition_id: editionId,
      sponsor_id: sponsorId,
      benefit_id: benefitId,
      body: { delivered_on: deliveredOn },
    });
  }

  removeBenefit(editionId: number, sponsorId: number, benefitId: number): Promise<SponsorDetail> {
    return this.api.invoke(manageSponsorsBenefitsRemove, {
      edition_id: editionId,
      sponsor_id: sponsorId,
      benefit_id: benefitId,
    });
  }

  levels(editionId: number): Promise<SponsorLevel[]> {
    return this.api.invoke(manageSponsorLevelsList, { edition_id: editionId });
  }

  createLevel(editionId: number, body: SponsorLevelWriteRequest): Promise<SponsorLevel[]> {
    return this.api.invoke(manageSponsorLevelsCreate, { edition_id: editionId, body });
  }

  updateLevel(
    editionId: number,
    levelId: number,
    body: PatchedSponsorLevelWriteRequest,
  ): Promise<SponsorLevel[]> {
    return this.api.invoke(manageSponsorLevelsUpdate, {
      edition_id: editionId,
      level_id: levelId,
      body,
    });
  }

  deleteLevel(editionId: number, levelId: number): Promise<SponsorLevel[]> {
    return this.api.invoke(manageSponsorLevelsDestroy, {
      edition_id: editionId,
      level_id: levelId,
    });
  }
}

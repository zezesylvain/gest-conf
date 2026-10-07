import { inject, Injectable } from '@angular/core';
import {
  Announcement,
  AnnouncementDetail,
  AnnouncementPreview,
  AnnouncementWriteRequest,
  Api,
  CancelledCount,
  PatchedAnnouncementWriteRequest,
  PatchedQuestionWriteRequest,
  PatchedSurveyWriteRequest,
  Question,
  QuestionWriteRequest,
  Segment,
  Survey,
  SurveyCreateRequest,
  SurveyDetail,
  SurveyResults,
  manageAnnouncementsCancel,
  manageAnnouncementsCreate,
  manageAnnouncementsDestroy,
  manageAnnouncementsList,
  manageAnnouncementsPreview,
  manageAnnouncementsPublish,
  manageAnnouncementsRetrieve,
  manageAnnouncementsTest,
  manageAnnouncementsUpdate,
  manageAnnouncementsWithdraw,
  manageSegmentsList,
  manageSurveysCreate,
  manageSurveysDestroy,
  manageSurveysDuplicate,
  manageSurveysExport,
  manageSurveysList,
  manageSurveysPublish,
  manageSurveysQuestionsCreate,
  manageSurveysQuestionsDestroy,
  manageSurveysQuestionsUpdate,
  manageSurveysResults,
  manageSurveysRetrieve,
  manageSurveysUpdate,
} from '@gestconf/shared';

/**
 * Communication dans la gestion (plan L8, N10 à N12 ; client généré) : annonces, bandeau et
 * envois groupés (`communications.send`), questionnaires de satisfaction
 * (`surveys.manage`). La publication d'une annonce ou d'un questionnaire demande une
 * réauthentification récente, que l'intercepteur ouvre avant de rejouer la requête ; tout
 * est revérifié par le serveur (règle n° 2).
 */
@Injectable({ providedIn: 'root' })
export class CommunicationApi {
  private readonly api = inject(Api);

  // --- Annonces et envois groupés (N10, N11, RG-22) ------------------------------------------

  segments(editionId: number): Promise<Segment[]> {
    return this.api.invoke(manageSegmentsList, { edition_id: editionId });
  }

  announcements(editionId: number): Promise<Announcement[]> {
    return this.api.invoke(manageAnnouncementsList, { edition_id: editionId });
  }

  announcement(editionId: number, announcementId: number): Promise<AnnouncementDetail> {
    return this.api.invoke(manageAnnouncementsRetrieve, {
      edition_id: editionId,
      announcement_id: announcementId,
    });
  }

  createAnnouncement(
    editionId: number,
    body: AnnouncementWriteRequest,
  ): Promise<AnnouncementDetail> {
    return this.api.invoke(manageAnnouncementsCreate, { edition_id: editionId, body });
  }

  updateAnnouncement(
    editionId: number,
    announcementId: number,
    body: PatchedAnnouncementWriteRequest,
  ): Promise<AnnouncementDetail> {
    return this.api.invoke(manageAnnouncementsUpdate, {
      edition_id: editionId,
      announcement_id: announcementId,
      body,
    });
  }

  deleteAnnouncement(editionId: number, announcementId: number): Promise<void> {
    return this.api.invoke(manageAnnouncementsDestroy, {
      edition_id: editionId,
      announcement_id: announcementId,
    });
  }

  preview(
    editionId: number,
    announcementId: number,
    locale: 'fr' | 'en',
  ): Promise<AnnouncementPreview> {
    return this.api.invoke(manageAnnouncementsPreview, {
      edition_id: editionId,
      announcement_id: announcementId,
      locale,
    });
  }

  sendTest(editionId: number, announcementId: number): Promise<void> {
    return this.api.invoke(manageAnnouncementsTest, {
      edition_id: editionId,
      announcement_id: announcementId,
    });
  }

  publishAnnouncement(editionId: number, announcementId: number): Promise<AnnouncementDetail> {
    return this.api.invoke(manageAnnouncementsPublish, {
      edition_id: editionId,
      announcement_id: announcementId,
    });
  }

  withdrawAnnouncement(editionId: number, announcementId: number): Promise<AnnouncementDetail> {
    return this.api.invoke(manageAnnouncementsWithdraw, {
      edition_id: editionId,
      announcement_id: announcementId,
    });
  }

  cancelSending(editionId: number, announcementId: number): Promise<CancelledCount> {
    return this.api.invoke(manageAnnouncementsCancel, {
      edition_id: editionId,
      announcement_id: announcementId,
    });
  }

  // --- Questionnaires de satisfaction (N12, RG-21) ------------------------------------------

  surveys(editionId: number): Promise<Survey[]> {
    return this.api.invoke(manageSurveysList, { edition_id: editionId });
  }

  survey(editionId: number, surveyId: number): Promise<SurveyDetail> {
    return this.api.invoke(manageSurveysRetrieve, { edition_id: editionId, survey_id: surveyId });
  }

  createSurvey(editionId: number, body: SurveyCreateRequest): Promise<SurveyDetail> {
    return this.api.invoke(manageSurveysCreate, { edition_id: editionId, body });
  }

  updateSurvey(
    editionId: number,
    surveyId: number,
    body: PatchedSurveyWriteRequest,
  ): Promise<SurveyDetail> {
    return this.api.invoke(manageSurveysUpdate, {
      edition_id: editionId,
      survey_id: surveyId,
      body,
    });
  }

  deleteSurvey(editionId: number, surveyId: number): Promise<void> {
    return this.api.invoke(manageSurveysDestroy, { edition_id: editionId, survey_id: surveyId });
  }

  publishSurvey(editionId: number, surveyId: number): Promise<SurveyDetail> {
    return this.api.invoke(manageSurveysPublish, { edition_id: editionId, survey_id: surveyId });
  }

  duplicateSurvey(editionId: number, surveyId: number): Promise<SurveyDetail> {
    return this.api.invoke(manageSurveysDuplicate, { edition_id: editionId, survey_id: surveyId });
  }

  addQuestion(editionId: number, surveyId: number, body: QuestionWriteRequest): Promise<Question> {
    return this.api.invoke(manageSurveysQuestionsCreate, {
      edition_id: editionId,
      survey_id: surveyId,
      body,
    });
  }

  updateQuestion(
    editionId: number,
    surveyId: number,
    questionId: number,
    body: PatchedQuestionWriteRequest,
  ): Promise<Question> {
    return this.api.invoke(manageSurveysQuestionsUpdate, {
      edition_id: editionId,
      survey_id: surveyId,
      question_id: questionId,
      body,
    });
  }

  deleteQuestion(editionId: number, surveyId: number, questionId: number): Promise<void> {
    return this.api.invoke(manageSurveysQuestionsDestroy, {
      edition_id: editionId,
      survey_id: surveyId,
      question_id: questionId,
    });
  }

  results(editionId: number, surveyId: number): Promise<SurveyResults> {
    return this.api.invoke(manageSurveysResults, { edition_id: editionId, survey_id: surveyId });
  }

  exportSurvey(editionId: number, surveyId: number, fileFormat: 'csv' | 'xlsx'): Promise<Blob> {
    return this.api.invoke(manageSurveysExport, {
      edition_id: editionId,
      survey_id: surveyId,
      file_format: fileFormat,
    });
  }
}

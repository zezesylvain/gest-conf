import { inject, Injectable } from '@angular/core';
import {
  Api,
  MyDietary,
  MyDietaryWriteRequest,
  MySurvey,
  MySurveyDetail,
  MyVisit,
  Subscription,
  Unsubscribed,
  VisitSpeakerWriteRequest,
  meAnnouncementsSubscription,
  meAnnouncementsSubscriptionUpdate,
  meDietaryRetrieve,
  meDietaryUpdate,
  meDietaryWithdraw,
  meSurveyAnswer,
  meSurveyRetrieve,
  meSurveys,
  meVisitRetrieve,
  meVisitUpdate,
  publicAnnouncementsUnsubscribe,
} from '@gestconf/shared';

/**
 * Espace compte du lot L8 (client généré) : « Ma venue » de l'intervenant invité (N6),
 * régime alimentaire (N7, RG-23), abonnement aux annonces (N11), questionnaires de
 * satisfaction (N12, RG-21), désabonnement par lien signé. Le serveur décide de tout
 * (404 pour qui n'est pas concerné, consentement exigé à chaque déclaration).
 */
@Injectable({ providedIn: 'root' })
export class CommunityService {
  private readonly api = inject(Api);

  visit(editionId: number): Promise<MyVisit> {
    return this.api.invoke(meVisitRetrieve, { edition_id: editionId });
  }

  updateVisit(editionId: number, body: VisitSpeakerWriteRequest): Promise<MyVisit> {
    return this.api.invoke(meVisitUpdate, { edition_id: editionId, body });
  }

  dietary(editionId: number): Promise<MyDietary> {
    return this.api.invoke(meDietaryRetrieve, { edition_id: editionId });
  }

  declareDietary(editionId: number, body: MyDietaryWriteRequest): Promise<MyDietary> {
    return this.api.invoke(meDietaryUpdate, { edition_id: editionId, body });
  }

  withdrawDietary(editionId: number): Promise<MyDietary> {
    return this.api.invoke(meDietaryWithdraw, { edition_id: editionId });
  }

  subscription(editionId: number): Promise<Subscription> {
    return this.api.invoke(meAnnouncementsSubscription, { edition_id: editionId });
  }

  setSubscription(editionId: number, subscribed: boolean): Promise<Subscription> {
    return this.api.invoke(meAnnouncementsSubscriptionUpdate, {
      edition_id: editionId,
      body: { subscribed },
    });
  }

  surveys(): Promise<MySurvey[]> {
    return this.api.invoke(meSurveys, {});
  }

  survey(surveyId: number): Promise<MySurveyDetail> {
    return this.api.invoke(meSurveyRetrieve, { survey_id: surveyId });
  }

  answer(surveyId: number, answers: Record<string, unknown>): Promise<MySurvey> {
    return this.api.invoke(meSurveyAnswer, { survey_id: surveyId, body: { answers } });
  }

  unsubscribe(token: string): Promise<Unsubscribed> {
    return this.api.invoke(publicAnnouncementsUnsubscribe, { body: { token } });
  }
}

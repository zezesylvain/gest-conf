import { Routes } from '@angular/router';

import { SubmissionPage } from './submission-page';
import { SubmissionsPage } from './submissions-page';

/**
 * Espace auteur /compte/soumissions (plan L3 §5). Les deux pages forment **un seul** morceau
 * chargé à la demande : chargées séparément, elles partageaient le client des soumissions,
 * que l'optimiseur remontait dans le bundle initial du portail (budget surveillé).
 */
export const submissionRoutes: Routes = [
  { path: '', title: 'portail.submissions.list.title', component: SubmissionsPage },
  { path: ':id', title: 'portail.submissions.edit.title', component: SubmissionPage },
];

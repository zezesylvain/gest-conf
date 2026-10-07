import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  OnInit,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { Router, RouterLink } from '@angular/router';
import {
  ErrorSummary,
  LanguageService,
  PageHeader,
  Question,
  QuestionKind,
  QuestionResult,
  Session,
  SurveyDetail,
  SurveyResults,
  SurveyScope,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { CommunicationApi } from '../../core/communication-api';
import { errorMessages } from '../../core/page-support';
import { ProgramApi } from '../../core/program-api';
import { saveBlob } from '../../core/registrations-api';
import { confirmAction } from '../events/events-support';
import { localLabel } from '../logistics/logistics-support';
import { choicesFrom, QUESTION_KINDS, SURVEY_SCOPES } from './communication-support';

/**
 * Fiche d'un questionnaire (plan L8, N12, **RG-21**) : textes, fenêtre à l'heure de
 * l'édition, portée ; questions (note, choix, texte), **verrouillées** dès la première
 * réponse (on duplique) ; publication sous réauthentification ; résultats agrégés à partir
 * du seuil de réponses, jamais une réponse isolée ; export avec les textes mélangés.
 */
@Component({
  selector: 'gestion-survey-detail-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './survey-detail-page.html',
  styleUrl: '../page.scss',
  styles: `
    .questions li {
      padding: 0.5rem 0;
      border-bottom: 1px solid var(--gc-border);
    }
    .bar {
      display: inline-block;
      height: 0.75rem;
      background: var(--gc-primary);
      border-radius: 0.25rem;
      vertical-align: middle;
    }
    .number {
      text-align: end;
    }
  `,
})
export class SurveyDetailPage implements OnInit {
  readonly editionId = input.required<string>();
  readonly surveyId = input.required<string>();

  private readonly api = inject(CommunicationApi);
  private readonly program = inject(ProgramApi);
  private readonly dialog = inject(MatDialog);
  private readonly router = inject(Router);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly kinds = QUESTION_KINDS;
  protected readonly scopes = SURVEY_SCOPES;
  protected readonly survey = signal<SurveyDetail | null>(null);
  protected readonly results = signal<SurveyResults | null>(null);
  protected readonly sessions = signal<Session[]>([]);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly isDraft = computed(() => this.survey()?.status === 'draft');

  private readonly fb = inject(NonNullableFormBuilder);
  protected readonly form = this.fb.group({
    title_fr: ['', [Validators.required, Validators.maxLength(150)]],
    title_en: ['', Validators.maxLength(150)],
    intro_fr: ['', Validators.maxLength(2000)],
    intro_en: ['', Validators.maxLength(2000)],
    opens_local: [''],
    closes_local: [''],
    scope: ['global' as SurveyScope],
    session: [null as number | null],
  });
  protected readonly questionForm = this.fb.group({
    kind: ['rating' as QuestionKind],
    label_fr: ['', [Validators.required, Validators.maxLength(300)]],
    label_en: ['', Validators.maxLength(300)],
    required: [true],
    choices_fr: [''],
    choices_en: [''],
  });

  async ngOnInit(): Promise<void> {
    const edition = this.edition();
    try {
      this.show(await this.api.survey(edition, this.id()));
      await this.loadResults();
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
    try {
      this.sessions.set((await this.program.board(edition)).sessions);
    } catch {
      this.sessions.set([]);
    }
    this.loading.set(false);
  }

  private edition(): number {
    return Number(this.editionId());
  }

  private id(): number {
    return Number(this.surveyId());
  }

  protected text(item: { label_fr: string; label_en: string }): string {
    return (this.language.current() === 'en' && item.label_en) || item.label_fr;
  }

  protected sessionTitle(session: Session): string {
    return (this.language.current() === 'en' && session.title_en) || session.title_fr;
  }

  protected local(value: string | null): string {
    return localLabel(value, this.language.current());
  }

  protected choices(question: Question): string {
    return question.choices.map((choice) => this.text(choice)).join(' · ');
  }

  /** Largeur de la barre d'un décompte (part des réponses à la question). */
  protected share(result: QuestionResult, count: number): number {
    return result.answers ? Math.round((count / result.answers) * 100) : 0;
  }

  protected async save(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    // Publié : seuls les titres, l'introduction et la clôture changent encore.
    const body = this.isDraft()
      ? {
          ...value,
          title_fr: value.title_fr.trim(),
          opens_local: value.opens_local || null,
          closes_local: value.closes_local || null,
          session: value.scope === 'session' ? value.session : null,
        }
      : {
          title_fr: value.title_fr.trim(),
          title_en: value.title_en,
          intro_fr: value.intro_fr,
          intro_en: value.intro_en,
          closes_local: value.closes_local || null,
        };
    await this.run('gestion.surveys.detail.saved', () =>
      this.api.updateSurvey(this.edition(), this.id(), body),
    );
  }

  protected async addQuestion(): Promise<void> {
    if (this.questionForm.invalid) {
      this.questionForm.markAllAsTouched();
      return;
    }
    const value = this.questionForm.getRawValue();
    const withChoices = value.kind === 'single' || value.kind === 'multiple';
    await this.run('gestion.surveys.detail.questionAdded', async () => {
      await this.api.addQuestion(this.edition(), this.id(), {
        kind: value.kind,
        label_fr: value.label_fr.trim(),
        label_en: value.label_en.trim(),
        required: value.required,
        ...(withChoices ? { choices: choicesFrom(value.choices_fr, value.choices_en) } : {}),
      });
      this.questionForm.reset();
      return this.api.survey(this.edition(), this.id());
    });
  }

  protected async toggleRequired(question: Question, required: boolean): Promise<void> {
    await this.run('gestion.surveys.detail.questionUpdated', async () => {
      await this.api.updateQuestion(this.edition(), this.id(), question.id, { required });
      return this.api.survey(this.edition(), this.id());
    });
  }

  protected async deleteQuestion(question: Question): Promise<void> {
    await this.run('gestion.surveys.detail.questionDeleted', async () => {
      await this.api.deleteQuestion(this.edition(), this.id(), question.id);
      return this.api.survey(this.edition(), this.id());
    });
  }

  protected async publish(): Promise<void> {
    const survey = this.survey();
    if (!survey) return;
    const answer = await confirmAction(
      this.dialog,
      this.translate,
      'gestion.surveys.detail.publish',
      { title: survey.title_fr },
    );
    if (!answer) return;
    await this.run('gestion.surveys.detail.published', () =>
      this.api.publishSurvey(this.edition(), this.id()),
    );
  }

  protected async duplicate(): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    try {
      const copy = await this.api.duplicateSurvey(this.edition(), this.id());
      await this.router.navigate([
        '/editions',
        this.editionId(),
        'communication',
        'questionnaires',
        copy.id,
      ]);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  protected async remove(): Promise<void> {
    const survey = this.survey();
    if (!survey) return;
    const answer = await confirmAction(this.dialog, this.translate, 'gestion.surveys.delete', {
      title: survey.title_fr,
    });
    if (!answer) return;
    this.busy.set(true);
    this.errors.set([]);
    try {
      await this.api.deleteSurvey(this.edition(), survey.id);
      await this.router.navigate([
        '/editions',
        this.editionId(),
        'communication',
        'questionnaires',
      ]);
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  protected async export(fileFormat: 'csv' | 'xlsx'): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    try {
      saveBlob(
        await this.api.exportSurvey(this.edition(), this.id(), fileFormat),
        `questionnaire.${fileFormat}`,
      );
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  private async loadResults(): Promise<void> {
    try {
      this.results.set(await this.api.results(this.edition(), this.id()));
    } catch {
      this.results.set(null);
    }
  }

  private async run(message: string, action: () => Promise<SurveyDetail>): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      this.show(await action());
      this.status.set(this.translate.instant(message));
    } catch (error) {
      // Erreurs de champ du serveur au résumé : ces formulaires n'en affichent pas sous
      // leurs champs.
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }

  private show(survey: SurveyDetail): void {
    this.survey.set(survey);
    this.form.reset({
      title_fr: survey.title_fr,
      title_en: survey.title_en,
      intro_fr: survey.intro_fr,
      intro_en: survey.intro_en,
      opens_local: survey.opens_local ?? '',
      closes_local: survey.closes_local ?? '',
      scope: survey.scope,
      session: survey.session,
    });
    this.form.enable();
    if (survey.status !== 'draft') {
      for (const name of ['opens_local', 'scope', 'session'] as const) {
        this.form.controls[name].disable();
      }
    }
  }
}

import { ChangeDetectionStrategy, Component, inject, input, OnInit, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { Router, RouterLink } from '@angular/router';
import {
  ErrorSummary,
  LanguageService,
  PageHeader,
  Session,
  Survey,
  SurveyScope,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { CommunicationApi } from '../../core/communication-api';
import { errorMessages } from '../../core/page-support';
import { ProgramApi } from '../../core/program-api';
import { localLabel } from '../logistics/logistics-support';
import { SURVEY_SCOPES } from './communication-support';

/**
 * Questionnaires de satisfaction (plan L8, N12 ; `surveys.manage`) : portée, fenêtre à
 * l'heure de l'édition, invités, réponses ; création avec le modèle par défaut, puis fiche.
 */
@Component({
  selector: 'gestion-surveys-page',
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
  templateUrl: './surveys-page.html',
  styleUrl: '../page.scss',
})
export class SurveysPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(CommunicationApi);
  private readonly program = inject(ProgramApi);
  private readonly router = inject(Router);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly scopes = SURVEY_SCOPES;
  protected readonly surveys = signal<Survey[]>([]);
  protected readonly sessions = signal<Session[]>([]);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);

  protected readonly form = inject(NonNullableFormBuilder).group({
    title_fr: ['', [Validators.required, Validators.maxLength(150)]],
    scope: ['global' as SurveyScope],
    session: [null as number | null],
    default_questions: [true],
  });

  async ngOnInit(): Promise<void> {
    const edition = Number(this.editionId());
    try {
      this.surveys.set(await this.api.surveys(edition));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
    try {
      // Sessions du programme, pour un questionnaire de session (lecture du programme).
      this.sessions.set((await this.program.board(edition)).sessions);
    } catch {
      this.sessions.set([]);
    }
    this.loading.set(false);
  }

  protected title(item: { title_fr: string; title_en: string }): string {
    return (this.language.current() === 'en' && item.title_en) || item.title_fr;
  }

  protected local(value: string | null): string {
    return localLabel(value, this.language.current());
  }

  protected async create(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    this.busy.set(true);
    this.errors.set([]);
    try {
      const created = await this.api.createSurvey(Number(this.editionId()), {
        title_fr: value.title_fr.trim(),
        scope: value.scope,
        session: value.scope === 'session' ? value.session : null,
        default_questions: value.default_questions,
      });
      await this.router.navigate([
        '/editions',
        this.editionId(),
        'communication',
        'questionnaires',
        created.id,
      ]);
    } catch (error) {
      // Erreurs de champ du serveur au résumé : ce formulaire n'en affiche pas sous ses champs.
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }
}

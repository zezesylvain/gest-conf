import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { ActivatedRoute, RouterLink } from '@angular/router';
import {
  ErrorSummary,
  LanguageService,
  MySurveyDetail,
  PageHeader,
  Question,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { CommunityService } from './community.service';
import { messagesOf } from './community-support';

export const TEXT_MAX = 1000;
const RATINGS = [1, 2, 3, 4, 5] as const;

/**
 * Réponse à un questionnaire de satisfaction (plan L8, N12, **RG-21**) : une seule réponse,
 * enregistrée **sans lien** avec la personne ; la page le dit, et prévient que les
 * commentaires libres seront lus par le comité. Note de 1 à 5 en boutons radio, choix
 * unique ou multiple, texte de 1 000 caractères au plus ; obligatoires revérifiées au
 * serveur.
 */
@Component({
  selector: 'portail-survey-page',
  imports: [RouterLink, TranslatePipe, MatButtonModule, ErrorSummary, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <p>
      <a routerLink="/compte/questionnaires">{{ 'portail.community.surveys.back' | translate }}</a>
    </p>
    @if (survey(); as current) {
      <gc-page-header [heading]="text(current, 'title')" />
      <p>{{ text(current, 'intro') }}</p>
      <p class="notice">{{ 'portail.community.surveys.anonymity' | translate }}</p>
      <gc-error-summary [messages]="errors()" />
      @if (done() || current.answered) {
        <p role="status">{{ 'portail.community.surveys.thanks' | translate }}</p>
      } @else if (!current.is_open) {
        <p>{{ 'portail.community.surveys.closed' | translate }}</p>
      } @else {
        <form (submit)="$event.preventDefault(); submit()">
          @for (question of current.questions; track question.id; let index = $index) {
            <fieldset class="question" [attr.aria-required]="question.required">
              <legend>
                {{ index + 1 }}. {{ text(question, 'label') }}
                @if (question.required) {
                  <span aria-hidden="true">*</span>
                  <span class="visually-hidden">{{
                    'portail.community.surveys.required' | translate
                  }}</span>
                }
              </legend>
              @switch (question.kind) {
                @case ('rating') {
                  <div class="scale">
                    @for (value of ratings; track value) {
                      <label>
                        <input
                          type="radio"
                          [name]="'q' + question.id"
                          [value]="value"
                          [checked]="answers()[question.id] === value"
                          (change)="set(question, value)"
                        />
                        {{ value }}
                      </label>
                    }
                  </div>
                  <p class="muted">{{ 'portail.community.surveys.scale' | translate }}</p>
                }
                @case ('single') {
                  @for (choice of question.choices; track choice.value) {
                    <label class="choice">
                      <input
                        type="radio"
                        [name]="'q' + question.id"
                        [value]="choice.value"
                        [checked]="answers()[question.id] === choice.value"
                        (change)="set(question, choice.value)"
                      />
                      {{ text(choice, 'label') }}
                    </label>
                  }
                }
                @case ('multiple') {
                  @for (choice of question.choices; track choice.value) {
                    <label class="choice">
                      <input
                        type="checkbox"
                        [value]="choice.value"
                        [checked]="picked(question, choice.value)"
                        (change)="pick(question, choice.value, $any($event.target).checked)"
                      />
                      {{ text(choice, 'label') }}
                    </label>
                  }
                }
                @case ('text') {
                  <textarea
                    rows="4"
                    [attr.maxlength]="textMax"
                    [attr.aria-label]="text(question, 'label')"
                    (input)="set(question, $any($event.target).value)"
                  ></textarea>
                  <p class="muted">{{ 'portail.community.surveys.textHint' | translate }}</p>
                }
              }
            </fieldset>
          }
          <button mat-flat-button type="submit" [disabled]="busy()">
            {{ 'portail.community.surveys.send' | translate }}
          </button>
        </form>
      }
    } @else if (loading()) {
      <p role="status">{{ 'portail.account.home.loading' | translate }}</p>
    } @else {
      <gc-error-summary [messages]="errors()" />
    }
  `,
  styleUrl: './community.scss',
  styles: `
    .choice {
      display: block;
      padding: 0.25rem 0;
    }
    textarea {
      width: 100%;
      font: inherit;
    }
    .visually-hidden {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
      white-space: nowrap;
    }
  `,
})
export class SurveyPage implements OnInit {
  private readonly service = inject(CommunityService);
  private readonly translate = inject(TranslateService);
  private readonly language = inject(LanguageService);
  private readonly id = Number(inject(ActivatedRoute).snapshot.paramMap.get('surveyId'));

  protected readonly ratings = RATINGS;
  protected readonly textMax = TEXT_MAX;
  protected readonly survey = signal<MySurveyDetail | null>(null);
  protected readonly answers = signal<Record<number, unknown>>({});
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly done = signal(false);
  protected readonly errors = signal<string[]>([]);

  async ngOnInit(): Promise<void> {
    try {
      this.survey.set(await this.service.survey(this.id));
    } catch (error) {
      this.errors.set(messagesOf(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  protected text(item: object, field: string): string {
    const record = item as Record<string, unknown>;
    const value = record[`${field}_${this.language.current()}`];
    return (typeof value === 'string' && value) || String(record[`${field}_fr`] ?? '');
  }

  protected set(question: Question, value: unknown): void {
    this.answers.update((current) => ({ ...current, [question.id]: value }));
  }

  protected picked(question: Question, value: string): boolean {
    const current = this.answers()[question.id];
    return Array.isArray(current) && current.includes(value);
  }

  protected pick(question: Question, value: string, checked: boolean): void {
    const current = (this.answers()[question.id] as string[] | undefined) ?? [];
    const next = current.filter((item) => item !== value);
    this.set(question, checked ? [...next, value] : next);
  }

  protected async submit(): Promise<void> {
    const survey = this.survey();
    if (!survey) return;
    const missing = survey.questions.filter((question) => {
      const value = this.answers()[question.id];
      return (
        question.required &&
        (value === undefined || value === '' || (Array.isArray(value) && !value.length))
      );
    });
    if (missing.length) {
      this.errors.set(
        missing.map((question) =>
          this.translate.instant('portail.community.surveys.missing', {
            label: this.text(question, 'label'),
          }),
        ),
      );
      return;
    }
    this.busy.set(true);
    this.errors.set([]);
    try {
      await this.service.answer(survey.id, this.answers());
      this.done.set(true);
    } catch (error) {
      this.errors.set(messagesOf(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }
}

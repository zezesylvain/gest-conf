import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import {
  apiErrorMessage,
  countryOptions,
  ErrorSummary,
  formatInZone,
  GcApiError,
  LanguageService,
  PageHeader,
  PublicEdition,
  Submission,
  SubmissionCheck,
  Timeline,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';
import { debounceTime, merge } from 'rxjs';

import { SubmissionsService, wordCount } from './submissions.service';

export const STEPS = ['info', 'authors', 'file', 'declarations', 'review'] as const;
export type Step = (typeof STEPS)[number];

/** Délai de la sauvegarde automatique après la dernière frappe. */
export const AUTOSAVE_DELAY_MS = 1200;

/**
 * Assistant de soumission (plan L3 §5) : informations → auteurs → fichier → déclarations →
 * récapitulatif. Informations et déclarations sont enregistrées automatiquement ; les auteurs
 * et le fichier, par une action explicite. Les écritures sont **sérialisées** et portent la
 * révision lue (If-Match) : un 412 signale une modification faite ailleurs (autre onglet).
 * Le serveur reste juge de la complétude (RG-01) et de la fenêtre d'écriture (RG-02).
 */
@Component({
  selector: 'portail-submission-page',
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
  templateUrl: './submission-page.html',
  styleUrl: './submission-page.scss',
})
export class SubmissionPage implements OnInit {
  /** Identifiant de la route (`:id`) ; le portail ne lie pas les paramètres aux entrées. */
  private readonly id = Number(inject(ActivatedRoute).snapshot.paramMap.get('id'));

  private readonly service = inject(SubmissionsService);
  private readonly translate = inject(TranslateService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly fb = inject(NonNullableFormBuilder);
  protected readonly language = inject(LanguageService);

  protected readonly steps = STEPS;
  protected readonly step = signal<Step>('info');
  protected readonly submission = signal<Submission | null>(null);
  protected readonly edition = signal<PublicEdition | null>(null);
  protected readonly check = signal<SubmissionCheck | null>(null);
  protected readonly timeline = signal<Timeline | null>(null);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal('');
  protected readonly saveState = signal<'idle' | 'saving' | 'saved' | 'conflict' | 'error'>('idle');
  protected readonly savedAt = signal<string>('');

  protected readonly countries = computed(() => countryOptions(this.language.current()));
  protected readonly editable = computed(() => this.submission()?.can_edit ?? false);
  protected readonly selectedType = computed(() => {
    const code = this.submission()?.submission_type;
    return this.edition()?.submission_types.find((type) => type.code === code) ?? null;
  });

  protected readonly info = this.fb.group({
    title: ['', Validators.maxLength(300)],
    abstract: [''],
    keywords: [''],
    language: [''],
    track: [''],
    submission_type: [''],
  });
  protected readonly declarations = this.fb.record<boolean>({});
  protected readonly authors = this.fb.array([this.authorGroup()]);
  /** Groupe porteur du tableau : sans `[formGroup]`, le formulaire n'émet pas `ngSubmit`. */
  protected readonly authorsForm = this.fb.group({ authors: this.authors });
  protected readonly withdrawReason = this.fb.control('', Validators.maxLength(2000));
  protected readonly words = signal(0);

  /** File d'écriture : chaque écriture attend la précédente et part avec la révision lue. */
  private queue: Promise<unknown> = Promise.resolve();

  async ngOnInit(): Promise<void> {
    try {
      const [submission, edition] = await Promise.all([
        this.service.get(this.id),
        this.service.currentEdition().catch(() => null),
      ]);
      this.edition.set(edition);
      this.load(submission);
      await this.refreshSide();
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.loading.set(false);
    }
    merge(this.info.valueChanges, this.declarations.valueChanges)
      .pipe(debounceTime(AUTOSAVE_DELAY_MS), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => void this.autosave());
    this.info.controls.abstract.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((text) => this.words.set(wordCount(text)));
  }

  protected authorGroup() {
    return this.fb.group({
      first_name: ['', [Validators.required, Validators.maxLength(150)]],
      last_name: ['', [Validators.required, Validators.maxLength(150)]],
      email: ['', [Validators.required, Validators.email]],
      institution: ['', Validators.maxLength(255)],
      country: [''],
      is_corresponding: [false],
      is_presenter: [false],
    });
  }

  /** Remplit les formulaires depuis la réponse du serveur, sans relancer la sauvegarde. */
  private load(submission: Submission): void {
    this.submission.set(submission);
    this.info.reset(
      {
        title: submission.title,
        abstract: submission.abstract,
        keywords: submission.keywords.join(', '),
        language: submission.language,
        track: submission.track ?? '',
        submission_type: submission.submission_type ?? '',
      },
      { emitEvent: false },
    );
    this.words.set(wordCount(submission.abstract));
    for (const declaration of submission.declarations) {
      if (!this.declarations.contains(declaration.code)) {
        this.declarations.addControl(declaration.code, this.fb.control(false), {
          emitEvent: false,
        });
      }
      this.declarations.controls[declaration.code].setValue(declaration.accepted, {
        emitEvent: false,
      });
    }
    this.authors.clear({ emitEvent: false });
    for (const author of submission.authors) {
      const group = this.authorGroup();
      group.reset(
        {
          first_name: author.first_name,
          last_name: author.last_name,
          email: author.email,
          institution: author.institution ?? '',
          country: author.country ?? '',
          is_corresponding: author.is_corresponding ?? false,
          is_presenter: author.is_presenter ?? false,
        },
        { emitEvent: false },
      );
      this.authors.push(group, { emitEvent: false });
    }
    const disable = !submission.can_edit;
    for (const form of [this.info, this.declarations, this.authors]) {
      if (disable) {
        form.disable({ emitEvent: false });
      } else {
        form.enable({ emitEvent: false });
      }
    }
  }

  private async refreshSide(): Promise<void> {
    const id = this.submission()?.id;
    if (!id) return;
    const [check, timeline] = await Promise.all([
      this.service.check(id),
      this.service.timeline(id),
    ]);
    this.check.set(check);
    this.timeline.set(timeline);
  }

  /** Écriture sérialisée : la révision est lue au moment de partir, jamais avant. */
  private write(action: (current: Submission) => Promise<Submission>): Promise<boolean> {
    const run = async (): Promise<boolean> => {
      const current = this.submission();
      if (!current) return false;
      this.saveState.set('saving');
      try {
        const updated = await action(current);
        this.submission.set(updated);
        this.saveState.set('saved');
        this.savedAt.set(
          formatInZone(updated.updated_at, this.edition()?.timezone, this.language.current()),
        );
        void this.refreshSide();
        return true;
      } catch (error) {
        if (error instanceof GcApiError && error.status === 412) {
          this.saveState.set('conflict');
        } else {
          this.saveState.set('error');
          this.errors.set([
            apiErrorMessage(this.translate, error),
            ...(error instanceof GcApiError ? Object.values(error.fields).flat() : []),
          ]);
        }
        return false;
      }
    };
    const next = this.queue.then(run, run);
    this.queue = next;
    return next;
  }

  private infoBody() {
    const value = this.info.getRawValue();
    return {
      title: value.title,
      abstract: value.abstract,
      keywords: value.keywords
        .split(/[,;\n]/)
        .map((keyword) => keyword.trim())
        .filter(Boolean),
      language: value.language,
      track: value.track || null,
      submission_type: value.submission_type || null,
      declarations: this.declarations.getRawValue(),
    };
  }

  protected async autosave(): Promise<void> {
    if (!this.editable() || (!this.info.dirty && !this.declarations.dirty)) return;
    this.errors.set([]);
    const saved = await this.write((current) => this.service.update(current, this.infoBody()));
    if (saved) {
      this.info.markAsPristine();
      this.declarations.markAsPristine();
    }
  }

  /** Après un 412 : relire la soumission (les modifications locales non enregistrées sont
   * abandonnées, l'auteur le sait par le message). */
  protected async reload(): Promise<void> {
    const current = this.submission();
    if (!current) return;
    this.load(await this.service.get(current.id));
    this.saveState.set('idle');
    await this.refreshSide();
  }

  protected addAuthor(): void {
    this.authors.push(this.authorGroup());
  }

  protected removeAuthor(index: number): void {
    this.authors.removeAt(index);
  }

  protected moveAuthor(index: number, delta: -1 | 1): void {
    const target = index + delta;
    if (target < 0 || target >= this.authors.length) return;
    const control = this.authors.at(index);
    this.authors.removeAt(index);
    this.authors.insert(target, control);
  }

  protected async saveAuthors(): Promise<void> {
    this.errors.set([]);
    if (this.authors.invalid) {
      this.authors.markAllAsTouched();
      return;
    }
    const authors = this.authors.getRawValue();
    if (await this.write((current) => this.service.setAuthors(current, authors))) {
      this.notice.set(this.translate.instant('portail.submissions.authors.saved'));
    }
  }

  protected async uploadFile(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    this.errors.set([]);
    await this.autosave(); // le type choisi doit être enregistré avant le dépôt
    if (await this.write((current) => this.service.upload(current, file))) {
      this.notice.set(this.translate.instant('portail.submissions.file.saved'));
    }
    input.value = '';
  }

  protected async removeFile(): Promise<void> {
    await this.write((current) => this.service.removeFile(current));
  }

  protected fileUrl(): string {
    return this.service.fileUrl(this.id);
  }

  protected async submit(): Promise<void> {
    this.errors.set([]);
    await this.autosave();
    await this.queue;
    const current = this.submission();
    if (!current) return;
    this.busy.set(true);
    try {
      this.load(await this.service.submit(current.id));
      this.notice.set(
        this.translate.instant('portail.submissions.review.submitted', {
          reference: this.submission()?.reference,
        }),
      );
      await this.refreshSide();
    } catch (error) {
      this.errors.set([
        apiErrorMessage(this.translate, error),
        ...(error instanceof GcApiError ? Object.values(error.fields).flat() : []),
      ]);
      await this.refreshSide();
    } finally {
      this.busy.set(false);
    }
  }

  protected async withdraw(): Promise<void> {
    const current = this.submission();
    if (!current) return;
    this.errors.set([]);
    this.busy.set(true);
    try {
      this.load(await this.service.withdraw(current.id, this.withdrawReason.value));
      this.notice.set(this.translate.instant('portail.submissions.withdraw.done'));
      await this.refreshSide();
    } catch (error) {
      this.errors.set([
        apiErrorMessage(this.translate, error),
        ...(error instanceof GcApiError ? Object.values(error.fields).flat() : []),
      ]);
    } finally {
      this.busy.set(false);
    }
  }

  protected async deleteDraft(): Promise<void> {
    const current = this.submission();
    if (!current) return;
    this.busy.set(true);
    try {
      await this.service.remove(current.id);
      await this.router.navigate(['/compte/soumissions']);
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.busy.set(false);
    }
  }

  protected when(iso: string | null | undefined): string {
    return iso ? formatInZone(iso, this.edition()?.timezone, this.language.current()) : '—';
  }

  protected localized(item: object, field: string): string {
    const record = item as Record<string, string | undefined>;
    const lang = this.language.current();
    return (lang === 'en' && record[`${field}_en`]) || record[`${field}_fr`] || '';
  }

  protected missingFields(): string[] {
    return Object.keys(this.check()?.missing ?? {});
  }

  protected missingMessages(): string[] {
    return Object.values(this.check()?.missing ?? {}).flat();
  }
}

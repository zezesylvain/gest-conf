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
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import {
  ErrorSummary,
  formatInZone,
  LanguageService,
  PageHeader,
  Signature,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { EventsApi, eventsUrls } from '../../core/events-api';
import { errorMessages } from '../../core/page-support';

/**
 * Ma signature (plan L7, K18) : le **signataire seul** renseigne, pour son propre compte,
 * le nom affiché, sa fonction en français et en anglais et l'image de sa signature (PNG
 * ou JPEG, type vérifié par le contenu, fichier privé). Le CO ne peut ni la déposer ni la
 * remplacer. Écritures avec réauthentification ; une pièce émise fige nom, fonction et
 * empreinte de l'image. `signature.manage`.
 */
@Component({
  selector: 'gestion-signature-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './signature-page.html',
  styleUrl: '../page.scss',
  styles: `
    .signature-preview {
      max-width: 20rem;
      max-height: 8rem;
      padding: 0.5rem;
      border: 1px solid var(--gc-border);
      background: #fff;
    }
  `,
})
export class SignaturePage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(EventsApi);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly signature = signal<Signature | null>(null);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly imageUrl = computed(() =>
    eventsUrls.signatureImage(this.editionId(), this.signature()?.image_uploaded_at ?? null),
  );
  protected readonly form = inject(NonNullableFormBuilder).group({
    display_name: ['', [Validators.required, Validators.maxLength(150)]],
    title_fr: ['', [Validators.required, Validators.maxLength(200)]],
    title_en: ['', [Validators.required, Validators.maxLength(200)]],
  });
  private file: File | null = null;

  async ngOnInit(): Promise<void> {
    try {
      this.apply(await this.api.signature(this.edition()));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected date(value: string | null): string {
    return value ? formatInZone(value, undefined, this.language.current()) : '—';
  }

  protected choose(event: Event): void {
    this.file = (event.target as HTMLInputElement).files?.[0] ?? null;
  }

  protected async save(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    await this.run('gestion.signature.saved', async () => {
      const value = this.form.getRawValue();
      this.apply(
        await this.api.updateSignature(this.edition(), {
          display_name: value.display_name.trim(),
          title_fr: value.title_fr.trim(),
          title_en: value.title_en.trim(),
        }),
      );
    });
  }

  protected async upload(): Promise<void> {
    if (!this.file) {
      this.errors.set([this.translate.instant('gestion.signature.image.missing')]);
      return;
    }
    const file = this.file;
    await this.run('gestion.signature.image.uploaded', async () => {
      this.apply(await this.api.uploadSignatureImage(this.edition(), file));
    });
  }

  private apply(signature: Signature): void {
    this.signature.set(signature);
    this.form.reset({
      display_name: signature.display_name,
      title_fr: signature.title_fr,
      title_en: signature.title_en,
    });
  }

  private async run(done: string, action: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      await action();
      this.status.set(this.translate.instant(done));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, this.form));
    } finally {
      this.busy.set(false);
    }
  }
}

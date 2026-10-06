import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  OnInit,
  signal,
} from '@angular/core';
import {
  FormControl,
  FormGroup,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import {
  CertificateSettings,
  DocumentNature,
  DocumentTemplate,
  ErrorSummary,
  formatInZone,
  LanguageService,
  PageHeader,
  SignatureLayout,
  Signatory,
  SigningMode,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { EventsApi, eventsUrls } from '../../core/events-api';
import { errorMessages } from '../../core/page-support';
import { confirmAction, DOCUMENT_NATURES, title } from './events-support';

const TEXT_FIELDS = [
  'title_fr',
  'title_en',
  'body_fr',
  'body_en',
  'footer_fr',
  'footer_en',
] as const;
type TextField = (typeof TEXT_FIELDS)[number];

type TemplateForm = FormGroup<
  Record<TextField, FormControl<string>> & { signatory: FormControl<number | null> }
>;

/**
 * Modèle des attestations et des lettres (plan L7, K9, K18, K19) : mode de signature (image
 * seule, PAdES avec le certificat de l'institution, prestataire qualifié à venir),
 * disposition, attestation d'évaluation (désactivée par défaut), en-tête officiel, et par
 * nature : **signataire désigné** parmi les comptes au rôle de signataire dont la signature
 * est complète, textes FR et EN à variables fermées, aperçu sur données fictives.
 * `certificates.manage` ; écritures avec réauthentification. Le CO ne dépose jamais la
 * signature d'un autre (K18) : elle vient de l'écran « Ma signature » du signataire.
 */
@Component({
  selector: 'gestion-certificate-settings-page',
  imports: [
    ReactiveFormsModule,
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
  templateUrl: './certificate-settings-page.html',
  styleUrl: '../page.scss',
  styles: `
    .header-preview {
      max-width: 100%;
      max-height: 6rem;
      border: 1px solid var(--gc-border);
    }
    textarea {
      min-height: 5rem;
    }
  `,
})
export class CertificateSettingsPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(EventsApi);
  private readonly dialog = inject(MatDialog);
  private readonly translate = inject(TranslateService);
  private readonly fb = inject(NonNullableFormBuilder);
  protected readonly language = inject(LanguageService);

  protected readonly modes: readonly SigningMode[] = ['image', 'pades', 'provider'];
  protected readonly layouts: readonly SignatureLayout[] = ['signature_right', 'signature_left'];
  protected readonly textFields = TEXT_FIELDS;
  protected readonly settings = signal<CertificateSettings | null>(null);
  protected readonly templates = signal<DocumentTemplate[]>([]);
  protected readonly signatories = signal<Signatory[]>([]);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  /** Version de l'en-tête affiché (recharge de l'image après remplacement). */
  protected readonly headerVersion = signal(0);
  protected readonly headerUrl = computed(() =>
    eventsUrls.header(this.editionId(), this.headerVersion()),
  );
  protected readonly settingsForm = this.fb.group({
    signing_mode: ['image' as SigningMode],
    layout: ['signature_right' as SignatureLayout],
    review_enabled: [false],
  });
  protected readonly keyForm = this.fb.group({
    password: ['', [Validators.required, Validators.maxLength(256)]],
  });
  private keyFile: File | null = null;
  private headerFile: File | null = null;
  protected readonly forms = new Map<DocumentNature, TemplateForm>();

  async ngOnInit(): Promise<void> {
    await this.run(async () => {
      const id = this.edition();
      const [settings, templates, signatories] = await Promise.all([
        this.api.certificateSettings(id),
        this.api.templates(id),
        this.api.signatories(id),
      ]);
      this.applySettings(settings);
      this.signatories.set(signatories);
      for (const template of templates) {
        this.forms.set(template.nature, this.templateForm(template));
      }
      this.templates.set(this.ordered(templates));
    }, false);
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected date(value: string | null): string {
    return value ? formatInZone(value, undefined, this.language.current()) : '—';
  }

  protected signatoryLabel(item: Signatory): string {
    const role = title(item, this.language.current());
    return role ? `${item.display_name} — ${role}` : item.display_name;
  }

  protected form(nature: DocumentNature): TemplateForm {
    return this.forms.get(nature)!;
  }

  protected previewUrl(nature: DocumentNature): string {
    return eventsUrls.preview(this.editionId(), nature);
  }

  protected placeholders(template: DocumentTemplate): string {
    return template.placeholders.map((name) => `{${name}}`).join(' ');
  }

  protected async saveSettings(): Promise<void> {
    await this.run(async () => {
      this.applySettings(
        await this.api.updateCertificateSettings(this.edition(), this.settingsForm.getRawValue()),
      );
      this.status.set(this.translate.instant('gestion.certificateSettings.saved'));
    });
  }

  protected chooseHeader(event: Event): void {
    this.headerFile = (event.target as HTMLInputElement).files?.[0] ?? null;
  }

  protected async uploadHeader(): Promise<void> {
    if (!this.headerFile) {
      this.errors.set([this.translate.instant('gestion.certificateSettings.header.missing')]);
      return;
    }
    const file = this.headerFile;
    await this.run(async () => {
      this.applySettings(await this.api.uploadHeader(this.edition(), file));
      this.headerVersion.update((value) => value + 1);
      this.status.set(this.translate.instant('gestion.certificateSettings.header.uploaded'));
    });
  }

  protected async deleteHeader(): Promise<void> {
    const answer = await confirmAction(
      this.dialog,
      this.translate,
      'gestion.certificateSettings.header.delete',
    );
    if (!answer) return;
    await this.run(async () => {
      this.applySettings(await this.api.deleteHeader(this.edition()));
      this.status.set(this.translate.instant('gestion.certificateSettings.header.deleted'));
    });
  }

  protected chooseKey(event: Event): void {
    this.keyFile = (event.target as HTMLInputElement).files?.[0] ?? null;
  }

  protected async uploadKey(): Promise<void> {
    if (!this.keyFile || this.keyForm.invalid) {
      this.keyForm.markAllAsTouched();
      if (!this.keyFile) {
        this.errors.set([this.translate.instant('gestion.certificateSettings.key.missing')]);
      }
      return;
    }
    const file = this.keyFile;
    await this.run(async () => {
      this.applySettings(
        await this.api.uploadSigningKey(this.edition(), file, this.keyForm.getRawValue().password),
      );
      // Le mot de passe ne sert qu'au dépôt : il n'est ni gardé ni réaffiché.
      this.keyForm.reset();
      this.status.set(this.translate.instant('gestion.certificateSettings.key.uploaded'));
    });
  }

  protected async deleteKey(): Promise<void> {
    const answer = await confirmAction(
      this.dialog,
      this.translate,
      'gestion.certificateSettings.key.delete',
    );
    if (!answer) return;
    await this.run(async () => {
      this.applySettings(await this.api.deleteSigningKey(this.edition()));
      this.status.set(this.translate.instant('gestion.certificateSettings.key.deleted'));
    });
  }

  protected async saveTemplate(template: DocumentTemplate): Promise<void> {
    const form = this.form(template.nature);
    if (form.invalid) {
      form.markAllAsTouched();
      return;
    }
    // Texte par défaut laissé tel quel : envoyé vide, il suit les évolutions du défaut au
    // lieu d'être figé comme texte propre à l'édition.
    const value = form.getRawValue();
    const body = { ...value };
    for (const field of TEXT_FIELDS) {
      if (!template.customized[field] && value[field].trim() === template[field].trim()) {
        body[field] = '';
      }
    }
    await this.run(
      async () => {
        const saved = await this.api.updateTemplate(this.edition(), template.nature, body);
        this.forms.set(saved.nature, this.templateForm(saved));
        this.templates.update((rows) =>
          rows.map((row) => (row.nature === saved.nature ? saved : row)),
        );
        this.status.set(
          this.translate.instant('gestion.certificateSettings.template.saved', {
            nature: this.translate.instant(`gestion.certificates.nature.${saved.nature}`),
          }),
        );
      },
      true,
      form,
    );
  }

  private templateForm(template: DocumentTemplate): TemplateForm {
    const text = (value: string, max: number) => [value, Validators.maxLength(max)];
    return this.fb.group({
      title_fr: text(template.title_fr, 200),
      title_en: text(template.title_en, 200),
      body_fr: text(template.body_fr, 2000),
      body_en: text(template.body_en, 2000),
      footer_fr: text(template.footer_fr, 500),
      footer_en: text(template.footer_en, 500),
      signatory: this.fb.control<number | null>(template.signatory?.id ?? null),
    }) as unknown as TemplateForm;
  }

  private ordered(templates: DocumentTemplate[]): DocumentTemplate[] {
    return [...templates].sort(
      (a, b) => DOCUMENT_NATURES.indexOf(a.nature) - DOCUMENT_NATURES.indexOf(b.nature),
    );
  }

  private applySettings(settings: CertificateSettings): void {
    this.settings.set(settings);
    this.settingsForm.reset({
      signing_mode: settings.signing_mode,
      layout: settings.layout,
      review_enabled: settings.review_enabled,
    });
  }

  private async run(action: () => Promise<void>, clear = true, form?: FormGroup): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    if (clear) this.status.set('');
    try {
      await action();
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error, form));
    } finally {
      this.busy.set(false);
    }
  }
}

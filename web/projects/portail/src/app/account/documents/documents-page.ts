import {
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import {
  apiErrorMessage,
  applyServerErrors,
  ErrorSummary,
  fieldErrorMessage,
  focusFirstInvalid,
  formatInZone,
  GcApiError,
  LanguageService,
  MyCertificate,
  MyLetter,
  MyRegistration,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { isActive, RegistrationService } from '../registration/registration.service';
import {
  badgeUrl,
  certificatePdfUrl,
  DocumentsService,
  formatDay,
  letterPdfUrl,
} from './documents.service';

/** Statuts de lettre qui permettent une nouvelle demande (refusée, révoquée). */
const REQUESTABLE: readonly string[] = ['refused', 'revoked'];

/**
 * « Mes documents » (plan L7, K15) : badge de l'inscription confirmée (PDF, généré à la
 * demande, jamais stocké : il porte le QR d'accès), attestations émises par le comité
 * (participation, communication, évaluation ; RG-16), lettre d'invitation pour le visa
 * (demande et suivi, K12). Chaque pièce porte un QR de vérification publique.
 */
@Component({
  selector: 'portail-documents-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './documents-page.html',
  styleUrl: './documents-page.scss',
})
export class DocumentsPage implements OnInit {
  private readonly service = inject(DocumentsService);
  private readonly registrationsApi = inject(RegistrationService);
  private readonly translate = inject(TranslateService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  protected readonly language = inject(LanguageService);

  protected readonly registrations = signal<MyRegistration[]>([]);
  protected readonly certificates = signal<MyCertificate[]>([]);
  protected readonly letter = signal<MyLetter | null>(null);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal('');
  protected readonly requesting = signal(false);

  /** Inscription en cours (une par édition) : badge et lettre d'invitation. */
  protected readonly active = computed(() => this.registrations().find(isActive) ?? null);
  /** Badges : inscriptions confirmées, dès que leur QR existe (K3). */
  protected readonly badges = computed(() =>
    this.registrations().filter((item) => item.status === 'confirmed' && item.has_qr),
  );
  /** Nouvelle demande : aucune lettre, ou la dernière refusée ou révoquée. */
  protected readonly canRequest = computed(() => {
    const letter = this.letter();
    return this.active() !== null && (letter === null || REQUESTABLE.includes(letter.status));
  });

  protected readonly letterForm = inject(NonNullableFormBuilder).group({
    passport_name: ['', [Validators.required, Validators.maxLength(200)]],
    nationality: ['', [Validators.required, Validators.maxLength(100)]],
    passport_number: ['', [Validators.required, Validators.maxLength(40)]],
    stay_from: ['', Validators.required],
    stay_to: ['', Validators.required],
    embassy: ['', [Validators.required, Validators.maxLength(300)]],
  });

  async ngOnInit(): Promise<void> {
    try {
      const [registrations, certificates] = await Promise.all([
        this.registrationsApi.list(),
        this.service.certificates(),
      ]);
      this.registrations.set(registrations);
      this.certificates.set(certificates);
      const active = this.active();
      if (active) {
        this.letter.set(await this.service.letter(active.id));
      }
    } catch (error) {
      this.errors.set([apiErrorMessage(this.translate, error)]);
    } finally {
      this.loading.set(false);
    }
  }

  protected badgeUrl(registration: MyRegistration): string {
    return badgeUrl(registration.id);
  }

  protected certificateUrl(certificate: MyCertificate): string {
    return certificatePdfUrl(certificate.id);
  }

  protected letterUrl(registration: MyRegistration): string {
    return letterPdfUrl(registration.id);
  }

  protected editionTitle(item: { edition_title_fr: string; edition_title_en: string }): string {
    return (this.language.current() === 'en' && item.edition_title_en) || item.edition_title_fr;
  }

  protected date(value: string | null): string {
    return value ? formatInZone(value, undefined, this.language.current()) : '';
  }

  protected day(value: string): string {
    return formatDay(value, this.language.current());
  }

  protected error(name: keyof typeof this.letterForm.controls): string {
    return fieldErrorMessage(this.translate, this.letterForm.controls[name]);
  }

  protected startRequest(): void {
    const previous = this.letter();
    // Après un refus : les données déjà saisies sont reprises, sauf le numéro de passeport
    // (jamais renvoyé en clair par le serveur).
    this.letterForm.reset({
      passport_name: previous?.passport_name ?? '',
      nationality: previous?.nationality ?? '',
      passport_number: '',
      stay_from: previous?.stay_from ?? '',
      stay_to: previous?.stay_to ?? '',
      embassy: previous?.embassy ?? '',
    });
    this.requesting.set(true);
  }

  protected async submitRequest(): Promise<void> {
    const active = this.active();
    if (!active) {
      return;
    }
    if (this.letterForm.invalid) {
      this.letterForm.markAllAsTouched();
      focusFirstInvalid(this.host.nativeElement);
      return;
    }
    this.busy.set(true);
    this.errors.set([]);
    this.notice.set('');
    try {
      const value = this.letterForm.getRawValue();
      this.letter.set(
        await this.service.requestLetter(active.id, {
          passport_name: value.passport_name.trim(),
          nationality: value.nationality.trim(),
          passport_number: value.passport_number.trim(),
          stay_from: value.stay_from,
          stay_to: value.stay_to,
          embassy: value.embassy.trim(),
        }),
      );
      this.requesting.set(false);
      this.letterForm.reset();
      this.notice.set(this.translate.instant('portail.documents.letter.requested'));
    } catch (error) {
      this.errors.set(this.messages(error));
      focusFirstInvalid(this.host.nativeElement);
    } finally {
      this.busy.set(false);
    }
  }

  /**
   * Erreurs de champ posées sur le formulaire ; refus de règle (409 : demande déjà en
   * cours, inscription annulée…) : le message du serveur, qui dit ce qui bloque.
   */
  private messages(error: unknown): string[] {
    if (!(error instanceof GcApiError)) {
      return [apiErrorMessage(this.translate, error)];
    }
    const unplaced = Object.keys(error.fields).length
      ? applyServerErrors(this.letterForm, error)
      : null;
    if (error.status === 409 && error.message) {
      return [error.message, ...(unplaced ?? [])];
    }
    return unplaced ?? [apiErrorMessage(this.translate, error)];
  }
}

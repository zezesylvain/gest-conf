import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import {
  ErrorSummary,
  formatInZone,
  KeyDate,
  KeyDateWriteRequest,
  LanguageService,
  PageHeader,
  toDateTimeLocalValue,
} from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { ItemListPage } from './item-list';

/** Codes réservés, dont le serveur connaît le sens et contrôle l'ordre (plan L1 §3.4). */
export const RESERVED_KEY_DATE_CODES = [
  'call_open',
  'call_close',
  'review_deadline',
  'notification',
  'camera_ready',
  'registration_open',
  'early_bird_end',
  'registration_close',
] as const;

function keyDateForm(builder: NonNullableFormBuilder) {
  return builder.group({
    code: [
      '',
      [Validators.required, Validators.maxLength(32), Validators.pattern(/^[-a-zA-Z0-9_]+$/)],
    ],
    at_local: ['', Validators.required],
    label_fr: ['', Validators.maxLength(255)],
    label_en: ['', Validators.maxLength(255)],
    is_public: [true],
    position: [0, [Validators.min(0), Validators.max(32767)]],
  });
}

/**
 * Calendrier (plan L1 §6.2, D13) : échéances **saisies à l'heure de l'édition**, converties
 * en UTC par le serveur (qui refuse une heure inexistante ou ambiguë au changement d'heure).
 * Double affichage : heure de l'édition et heure du navigateur.
 */
@Component({
  selector: 'gestion-calendar-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatFormFieldModule,
    MatInputModule,
    MatCheckboxModule,
    MatButtonModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './calendar-page.html',
  styleUrl: '../page.scss',
})
export class CalendarPage extends ItemListPage<KeyDate, ReturnType<typeof keyDateForm>> {
  protected readonly keys = 'gestion.settings.calendar';
  protected readonly form = keyDateForm(inject(NonNullableFormBuilder));
  protected readonly language = inject(LanguageService);
  protected readonly reservedCodes = RESERVED_KEY_DATE_CODES;
  protected readonly timeZone = signal('');
  protected readonly browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone;

  override async ngOnInit(): Promise<void> {
    try {
      this.timeZone.set((await this.api.edition(Number(this.editionId()))).timezone ?? '');
    } catch {
      // Erreur affichée par le chargement de la liste.
    }
    await super.ngOnInit();
  }

  protected inEdition(item: KeyDate): string {
    return formatInZone(item.at, this.timeZone() || undefined, this.language.current());
  }

  protected inBrowser(item: KeyDate): string {
    return formatInZone(item.at, undefined, this.language.current());
  }

  protected label(item: KeyDate): string {
    const own = this.language.current() === 'en' ? item.label_en || item.label_fr : item.label_fr;
    if (own) {
      return own;
    }
    const key = `gestion.keyDateCodes.${item.code}`;
    const translated = this.translate.instant(key);
    return translated !== key ? translated : item.code;
  }

  protected fetch(editionId: number) {
    return this.api.keyDates(editionId);
  }
  protected create(editionId: number, value: KeyDateWriteRequest) {
    return this.api.createKeyDate(editionId, value);
  }
  protected update(editionId: number, id: number, value: KeyDateWriteRequest) {
    return this.api.updateKeyDate(editionId, id, value);
  }
  protected remove(editionId: number, id: number) {
    return this.api.deleteKeyDate(editionId, id);
  }
  protected toFormValue(item: KeyDate) {
    return {
      code: item.code,
      at_local: toDateTimeLocalValue(item.at_local),
      label_fr: item.label_fr,
      label_en: item.label_en,
      is_public: item.is_public,
      position: item.position,
    };
  }
  protected emptyValue() {
    return { code: '', at_local: '', label_fr: '', label_en: '', is_public: true, position: 0 };
  }
  protected describe(item: KeyDate): string {
    return this.label(item);
  }
}

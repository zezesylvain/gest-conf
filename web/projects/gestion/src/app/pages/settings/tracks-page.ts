import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { ErrorSummary, PageHeader, Track, TrackRequest } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { ItemListPage } from './item-list';

const SLUG = /^[-a-zA-Z0-9_]+$/;

function trackForm(builder: NonNullableFormBuilder) {
  return builder.group({
    code: ['', [Validators.required, Validators.maxLength(32), Validators.pattern(SLUG)]],
    name_fr: ['', [Validators.required, Validators.maxLength(255)]],
    name_en: ['', Validators.maxLength(255)],
    description_fr: [''],
    description_en: [''],
    position: [0, [Validators.min(0), Validators.max(32767)]],
    is_active: [true],
  });
}

/** Thématiques de l'édition (plan L1 §6.1), bilingues ; désactiver plutôt que supprimer dès L3. */
@Component({
  selector: 'gestion-tracks-page',
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
  templateUrl: './tracks-page.html',
  styleUrl: '../page.scss',
})
export class TracksPage extends ItemListPage<Track, ReturnType<typeof trackForm>> {
  protected readonly keys = 'gestion.settings.tracks';
  protected readonly form = trackForm(inject(NonNullableFormBuilder));

  protected fetch(editionId: number) {
    return this.api.tracks(editionId);
  }
  protected create(editionId: number, value: TrackRequest) {
    return this.api.createTrack(editionId, value);
  }
  protected update(editionId: number, id: number, value: TrackRequest) {
    return this.api.updateTrack(editionId, id, value);
  }
  protected remove(editionId: number, id: number) {
    return this.api.deleteTrack(editionId, id);
  }
  protected toFormValue(item: Track) {
    return {
      code: item.code,
      name_fr: item.name_fr,
      name_en: item.name_en ?? '',
      description_fr: item.description_fr ?? '',
      description_en: item.description_en ?? '',
      position: item.position ?? 0,
      is_active: item.is_active ?? true,
    };
  }
  protected emptyValue() {
    return {
      code: '',
      name_fr: '',
      name_en: '',
      description_fr: '',
      description_en: '',
      position: this.items().length,
      is_active: true,
    };
  }
  protected describe(item: Track): string {
    return `${item.code} — ${item.name_fr}`;
  }
}

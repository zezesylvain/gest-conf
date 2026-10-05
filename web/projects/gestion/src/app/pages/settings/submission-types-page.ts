import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { ErrorSummary, PageHeader, SubmissionType, SubmissionTypeRequest } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { ItemListPage } from './item-list';

const SLUG = /^[-a-zA-Z0-9_]+$/;

function typeForm(builder: NonNullableFormBuilder) {
  return builder.group({
    code: ['', [Validators.required, Validators.maxLength(32), Validators.pattern(SLUG)]],
    label_fr: ['', [Validators.required, Validators.maxLength(255)]],
    label_en: ['', Validators.maxLength(255)],
    description_fr: [''],
    description_en: [''],
    default_duration_min: [20 as number | null, [Validators.min(1), Validators.max(600)]],
    abstract_max_words: [300, [Validators.min(0), Validators.max(5000)]],
    position: [0, [Validators.min(0), Validators.max(32767)]],
    is_active: [true],
  });
}

/** Types de communication (plan L1 §6.1) : durée par défaut, limite du résumé, bilingues. */
@Component({
  selector: 'gestion-submission-types-page',
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
  templateUrl: './submission-types-page.html',
  styleUrl: '../page.scss',
})
export class SubmissionTypesPage extends ItemListPage<SubmissionType, ReturnType<typeof typeForm>> {
  protected readonly keys = 'gestion.settings.types';
  protected readonly form = typeForm(inject(NonNullableFormBuilder));

  protected fetch(editionId: number) {
    return this.api.submissionTypes(editionId);
  }
  protected create(editionId: number, value: SubmissionTypeRequest) {
    return this.api.createSubmissionType(editionId, value);
  }
  protected update(editionId: number, id: number, value: SubmissionTypeRequest) {
    return this.api.updateSubmissionType(editionId, id, value);
  }
  protected remove(editionId: number, id: number) {
    return this.api.deleteSubmissionType(editionId, id);
  }
  protected toFormValue(item: SubmissionType) {
    return {
      code: item.code,
      label_fr: item.label_fr,
      label_en: item.label_en ?? '',
      description_fr: item.description_fr ?? '',
      description_en: item.description_en ?? '',
      default_duration_min: item.default_duration_min ?? null,
      abstract_max_words: item.abstract_max_words ?? 300,
      position: item.position ?? 0,
      is_active: item.is_active ?? true,
    };
  }
  protected emptyValue() {
    return {
      code: '',
      label_fr: '',
      label_en: '',
      description_fr: '',
      description_en: '',
      default_duration_min: 20,
      abstract_max_words: 300,
      position: this.items().length,
      is_active: true,
    };
  }
  protected describe(item: SubmissionType): string {
    return `${item.code} — ${item.label_fr}`;
  }
}

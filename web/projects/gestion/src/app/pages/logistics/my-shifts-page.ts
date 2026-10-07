import { ChangeDetectionStrategy, Component, inject, input, OnInit, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { ErrorSummary, LanguageService, PageHeader, Shift } from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { LogisticsApi } from '../../core/logistics-api';
import { errorMessages } from '../../core/page-support';
import { saveBlob } from '../../core/registrations-api';
import { localLabel } from './logistics-support';

/**
 * « Mon planning » du bénévole (plan L8, N9 ; `shifts.own`) : ses postes, à l'heure de
 * l'édition, et leur fichier iCal (générateur du programme, L5).
 */
@Component({
  selector: 'gestion-my-shifts-page',
  imports: [TranslatePipe, MatButtonModule, ErrorSummary, PageHeader],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './my-shifts-page.html',
  styleUrl: '../page.scss',
})
export class MyShiftsPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(LogisticsApi);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly shifts = signal<Shift[]>([]);
  protected readonly loading = signal(true);
  protected readonly errors = signal<string[]>([]);

  async ngOnInit(): Promise<void> {
    try {
      this.shifts.set(await this.api.myShifts(Number(this.editionId())));
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }

  protected local(value: string): string {
    return localLabel(value, this.language.current());
  }

  protected title(shift: Shift): string {
    return (this.language.current() === 'en' && shift.title_en) || shift.title_fr;
  }

  protected async calendar(): Promise<void> {
    try {
      saveBlob(await this.api.myCalendar(Number(this.editionId())), 'mon-planning.ics');
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }
}

import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { PublicProgramSlot } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { SiteLanguage } from '../site-pages';
import { inLanguage, timeIn } from './program-support';

/**
 * Créneaux d'une session publiée : heure, titre, auteurs (présentateurs signalés) ou
 * intervenant invité (biographie et photo selon ses consentements, I11). Jamais d'adresse.
 */
@Component({
  selector: 'portail-program-slot-list',
  imports: [TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (slots().length) {
      <ol class="slots">
        @for (slot of slots(); track slot.id) {
          <li>
            <span class="time">{{ time(slot.starts_at) }}</span>
            <div>
              <p class="slot-title">
                {{ title(slot) }}
                @if (slot.reference) {
                  <span class="meta">{{ slot.reference }}</span>
                }
              </p>
              @if (slot.authors.length) {
                <ul class="authors meta">
                  @for (author of slot.authors; track $index) {
                    <li [class.presenter]="author.presenter">
                      {{ author.name }}
                      @if (author.institution) {
                        ({{ author.institution }})
                      }
                      @if (author.presenter) {
                        <span class="visually-hidden">
                          — {{ 'portail.program.presenter' | translate }}</span
                        >
                      }
                    </li>
                  }
                </ul>
              }
              @if (slot.speaker; as speaker) {
                <div class="speaker">
                  @if (detailed() && speaker.photo_url) {
                    <img [src]="speaker.photo_url" alt="" width="64" height="64" />
                  }
                  <p class="meta">
                    {{ speaker.name }}
                    @if (speaker.institution) {
                      ({{ speaker.institution }})
                    }
                  </p>
                  @if (detailed() && speaker.bio) {
                    <p class="bio">{{ speaker.bio }}</p>
                  }
                </div>
              }
              @if (slot.type) {
                <p class="meta">{{ typeLabel(slot.type) }}</p>
              }
            </div>
          </li>
        }
      </ol>
    }
  `,
  styleUrl: './program.scss',
})
export class ProgramSlotList {
  readonly slots = input.required<PublicProgramSlot[]>();
  readonly timezone = input.required<string>();
  readonly language = input.required<SiteLanguage>();
  /** Fiche de session : photo et biographie des intervenants invités. */
  readonly detailed = input(false);

  protected time(iso: string): string {
    return timeIn(iso, this.timezone(), this.language());
  }

  protected title(slot: PublicProgramSlot): string {
    return inLanguage(slot.title, slot.title_en, this.language());
  }

  protected typeLabel(type: { label_fr: string; label_en: string }): string {
    return inLanguage(type.label_fr, type.label_en, this.language());
  }
}

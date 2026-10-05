import { NgTemplateOutlet } from '@angular/common';
import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { PublicSection } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { Countdown } from './countdown';
import { sanitizeHtml } from './sanitize';
import { localized, SiteLanguage } from './site-pages';
import { DatesList, DocumentsList, EditionHero, SubmissionTypesList, TracksList } from './widgets';

/**
 * Rendu des sections d'une page (plan L2 §2.2) : un bloc par type, **type inconnu ignoré**
 * (catalogue fermé). Le HTML des corps est réassaini ici, sans DOM (aussi au pré-rendu).
 */
@Component({
  selector: 'portail-sections',
  imports: [
    NgTemplateOutlet,
    TranslatePipe,
    Countdown,
    EditionHero,
    DatesList,
    TracksList,
    SubmissionTypesList,
    DocumentsList,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @for (section of sections(); track section.code) {
      @switch (section.section_type) {
        @case ('rich_text') {
          <section class="block rich" [attr.data-section]="section.code">
            <ng-container *ngTemplateOutlet="heading; context: { $implicit: section }" />
            <div class="prose" [innerHTML]="body(section)"></div>
            <ng-container *ngTemplateOutlet="buttons; context: { $implicit: section }" />
          </section>
        }
        @case ('cta_banner') {
          <section class="block banner" [attr.data-section]="section.code">
            <ng-container *ngTemplateOutlet="heading; context: { $implicit: section }" />
            <div class="prose" [innerHTML]="body(section)"></div>
            <ng-container *ngTemplateOutlet="buttons; context: { $implicit: section }" />
          </section>
        }
        @case ('image_text') {
          <section
            class="block image-text"
            [class.right]="section.config?.image_position === 'right'"
            [attr.data-section]="section.code"
          >
            @if (section.image; as image) {
              <img
                [src]="image.url"
                [attr.width]="image.width"
                [attr.height]="image.height"
                [alt]="text(image, 'title')"
                loading="lazy"
              />
            }
            <div>
              <ng-container *ngTemplateOutlet="heading; context: { $implicit: section }" />
              <div class="prose" [innerHTML]="body(section)"></div>
              <ng-container *ngTemplateOutlet="buttons; context: { $implicit: section }" />
            </div>
          </section>
        }
        @case ('edition_hero') {
          @if (section.data; as edition) {
            <portail-edition-hero [edition]="edition" [language]="language()" [level]="2">
              @if (section.config?.countdown !== false) {
                <portail-countdown [edition]="edition" [language]="language()" />
              }
            </portail-edition-hero>
          }
        }
        @case ('key_dates') {
          <section class="block" [attr.data-section]="section.code">
            <ng-container *ngTemplateOutlet="heading; context: { $implicit: section }" />
            <portail-dates-list
              [dates]="section.data ?? []"
              [language]="language()"
              [timezone]="timezone()"
            />
          </section>
        }
        @case ('tracks') {
          <section class="block" [attr.data-section]="section.code">
            <ng-container *ngTemplateOutlet="heading; context: { $implicit: section }" />
            <portail-tracks-list [tracks]="section.data ?? []" [language]="language()" />
          </section>
        }
        @case ('submission_types') {
          <section class="block" [attr.data-section]="section.code">
            <ng-container *ngTemplateOutlet="heading; context: { $implicit: section }" />
            <portail-submission-types-list [types]="section.data ?? []" [language]="language()" />
          </section>
        }
        @case ('documents') {
          <section class="block" [attr.data-section]="section.code">
            <ng-container *ngTemplateOutlet="heading; context: { $implicit: section }" />
            <portail-documents-list [documents]="section.data ?? []" [language]="language()" />
          </section>
        }
        @case ('committee') {
          <section class="block" [attr.data-section]="section.code">
            <ng-container *ngTemplateOutlet="heading; context: { $implicit: section }" />
            @if (!section.data?.length) {
              <p class="muted">{{ 'portail.site.committeeSoon' | translate }}</p>
            }
          </section>
        }
        <!-- Type inconnu : rien (catalogue fermé, plan L2 §2.2). -->
      }
    }

    <ng-template #heading let-section>
      @if (text(section, 'title')) {
        <h2>{{ text(section, 'title') }}</h2>
      }
      @if (text(section, 'subtitle')) {
        <p class="subtitle">{{ text(section, 'subtitle') }}</p>
      }
    </ng-template>
    <ng-template #buttons let-section>
      @if (
        (section.cta_url && text(section, 'cta_label')) ||
        (section.cta2_url && text(section, 'cta2_label'))
      ) {
        <p class="buttons">
          @if (section.cta_url && text(section, 'cta_label')) {
            <a class="button primary" [href]="section.cta_url">{{ text(section, 'cta_label') }}</a>
          }
          @if (section.cta2_url && text(section, 'cta2_label')) {
            <a class="button" [href]="section.cta2_url">{{ text(section, 'cta2_label') }}</a>
          }
        </p>
      }
    </ng-template>
  `,
  styleUrl: './site.scss',
})
export class SectionsView {
  readonly sections = input.required<PublicSection[]>();
  readonly language = input.required<SiteLanguage>();
  /** Fuseau de l'édition, pour les dates clés. */
  readonly timezone = input<string>('');

  protected text(item: object, field: string): string {
    return localized(item, field, this.language());
  }

  protected body(section: PublicSection): string {
    return sanitizeHtml(localized(section, 'body', this.language()));
  }
}

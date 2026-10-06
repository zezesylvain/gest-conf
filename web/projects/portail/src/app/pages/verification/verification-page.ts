import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  OnDestroy,
  OnInit,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Meta } from '@angular/platform-browser';
import { ActivatedRoute, Router } from '@angular/router';
import {
  apiErrorMessage,
  formatInZone,
  LanguageService,
  PublicVerification,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { DocumentsService, formatDay } from '../../account/documents/documents.service';

/** Code lisible (base32) : majuscules, sans espaces ni tirets ajoutés à la recopie. */
export function normalizeCode(value: string): string {
  return value.toUpperCase().replace(/[\s-]+/g, '');
}

/**
 * Vérification publique d'une attestation ou d'une lettre (plan L7, K10) : adresse du QR
 * imprimé sur la pièce, `/verification/<code>`. Rendue dans le navigateur (jamais
 * pré-rendue), `noindex`. Le serveur ne dit que la nature, le nom (absent si la personne
 * est anonymisée), l'édition, la date et le statut ; un code inconnu ou mal formé reçoit la
 * même réponse (pas d'énumération), et la vérification est limitée en débit.
 */
@Component({
  selector: 'portail-verification-page',
  imports: [ReactiveFormsModule, TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <h1>{{ 'portail.verification.title' | translate }}</h1>
    <p>{{ 'portail.verification.lead' | translate }}</p>

    <div aria-live="polite">
      @if (loading()) {
        <p role="status">{{ 'portail.verification.loading' | translate }}</p>
      } @else if (result(); as found) {
        <section
          class="result"
          [class.valid]="found.status === 'valid'"
          [class.revoked]="found.status === 'revoked'"
          aria-labelledby="result-title"
        >
          <h2 id="result-title">
            {{ 'portail.verification.status.' + found.kind + '.' + found.status | translate }}
          </h2>
          <dl>
            <dt>{{ 'portail.verification.fields.nature' | translate }}</dt>
            <dd>{{ 'portail.documents.nature.' + found.nature | translate }}</dd>
            <dt>{{ 'portail.verification.fields.holder' | translate }}</dt>
            <dd>{{ found.name ?? ('portail.verification.anonymized' | translate) }}</dd>
            <dt>{{ 'portail.verification.fields.edition' | translate }}</dt>
            <dd>
              {{ editionTitle(found) }}
              @if (found.edition_start && found.edition_end) {
                <br />{{ day(found.edition_start) }} → {{ day(found.edition_end) }}
              }
            </dd>
            <dt>{{ 'portail.verification.fields.issuedAt' | translate }}</dt>
            <dd>{{ date(found.issued_at) }}</dd>
            @if (found.revoked_at) {
              <dt>{{ 'portail.verification.fields.revokedAt' | translate }}</dt>
              <dd>{{ date(found.revoked_at) }}</dd>
            }
          </dl>
        </section>
      } @else if (notFound()) {
        <p class="result unknown" role="alert">{{ 'portail.verification.notFound' | translate }}</p>
      } @else if (error()) {
        <p class="result unknown" role="alert">{{ error() }}</p>
      }
    </div>

    <form [formGroup]="form" (ngSubmit)="submit()" novalidate>
      <label for="verification-code">{{ 'portail.verification.codeLabel' | translate }}</label>
      <div class="row">
        <input
          id="verification-code"
          formControlName="code"
          autocomplete="off"
          autocapitalize="characters"
          spellcheck="false"
          [attr.aria-describedby]="'verification-hint'"
        />
        <button type="submit">{{ 'portail.verification.submit' | translate }}</button>
      </div>
      <p id="verification-hint" class="hint">{{ 'portail.verification.codeHint' | translate }}</p>
    </form>
  `,
  styles: `
    :host {
      display: block;
      max-width: 44rem;
    }
    .result {
      margin: 1rem 0;
      padding: 1rem;
      border: 1px solid var(--gc-border);
      border-left-width: 0.5rem;
      border-radius: 0.25rem;
    }
    .valid {
      border-left-color: var(--gc-success);
    }
    .revoked,
    .unknown {
      border-left-color: var(--gc-danger);
    }
    h2 {
      margin-top: 0;
    }
    dl {
      display: grid;
      grid-template-columns: minmax(8rem, max-content) 1fr;
      gap: 0.35rem 1rem;
      margin: 0;
    }
    dt {
      font-weight: 600;
    }
    dd {
      margin: 0;
    }
    form {
      margin-top: 1.5rem;
    }
    .row {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-top: 0.25rem;
    }
    input {
      flex: 1 1 16rem;
      padding: 0.5rem;
      font: inherit;
      letter-spacing: 0.05em;
    }
    button {
      padding: 0.5rem 1rem;
      font: inherit;
      color: var(--gc-on-primary);
      background: var(--gc-primary);
      border: 0;
      border-radius: 0.25rem;
      cursor: pointer;
    }
    .hint {
      color: var(--gc-muted);
    }
  `,
})
export class VerificationPage implements OnInit, OnDestroy {
  private readonly service = inject(DocumentsService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly meta = inject(Meta);
  private readonly translate = inject(TranslateService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly language = inject(LanguageService);

  protected readonly result = signal<PublicVerification | null>(null);
  protected readonly notFound = signal(false);
  protected readonly error = signal('');
  protected readonly loading = signal(false);
  protected readonly form = inject(NonNullableFormBuilder).group({
    code: ['', [Validators.required, Validators.maxLength(64)]],
  });

  ngOnInit(): void {
    this.meta.updateTag({ name: 'robots', content: 'noindex, nofollow' });
    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      const code = normalizeCode(params.get('code') ?? '');
      this.form.reset({ code });
      if (code) {
        void this.check(code);
      } else {
        this.result.set(null);
        this.notFound.set(false);
      }
    });
  }

  ngOnDestroy(): void {
    this.meta.removeTag('name="robots"');
  }

  protected editionTitle(found: PublicVerification): string {
    return (this.language.current() === 'en' && found.edition_title_en) || found.edition_title_fr;
  }

  protected date(value: string): string {
    return formatInZone(value, undefined, this.language.current());
  }

  protected day(value: string): string {
    return formatDay(value, this.language.current());
  }

  protected submit(): void {
    const code = normalizeCode(this.form.getRawValue().code);
    if (!code) {
      this.form.markAllAsTouched();
      return;
    }
    void this.router.navigate(['/verification', code]);
  }

  private async check(code: string): Promise<void> {
    this.loading.set(true);
    this.result.set(null);
    this.notFound.set(false);
    this.error.set('');
    try {
      const found = await this.service.verify(code);
      this.result.set(found);
      this.notFound.set(found === null);
    } catch (error) {
      // Débit dépassé (429) ou serveur injoignable : message explicite.
      this.error.set(apiErrorMessage(this.translate, error));
    } finally {
      this.loading.set(false);
    }
  }
}

import {
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  HostListener,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed, toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';
import { filter, map } from 'rxjs';

import { helpForUrl } from '../core/navigation';
import { HELP_SHEETS_BY_ID } from './help-sheets';
import { HelpSheetView } from './help-sheet';

/**
 * Aide contextuelle (plan L2 §2.3) : bouton « ? » et tiroir, montés **une fois** dans la
 * coque. La fiche se déduit de l'URL par la table de navigation : aucun écran n'a
 * d'identifiant d'aide à déclarer. Un écran sans fiche n'affiche pas de bouton.
 */
@Component({
  selector: 'gestion-context-help',
  imports: [RouterLink, TranslatePipe, HelpSheetView],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (sheet(); as current) {
      <button
        #trigger
        type="button"
        class="help-button"
        aria-haspopup="dialog"
        [attr.aria-expanded]="open()"
        [attr.aria-label]="'gestion.help.open' | translate"
        (click)="show()"
      >
        ?
      </button>
      @if (open()) {
        <div class="backdrop" (click)="hide()" aria-hidden="true"></div>
        <aside
          #drawer
          class="drawer"
          role="dialog"
          aria-modal="false"
          [attr.aria-labelledby]="'tiroir-' + current.id + '-titre'"
        >
          <div class="drawer-bar">
            <a [routerLink]="['/aide']" [queryParams]="{ fiche: current.id }" (click)="hide()">
              {{ 'gestion.help.fullGuide' | translate }}
            </a>
            <button type="button" class="close" (click)="hide()">
              {{ 'gestion.help.close' | translate }}
            </button>
          </div>
          <gestion-help-sheet [sheet]="current" />
        </aside>
      }
    }
  `,
  styles: `
    .help-button {
      position: fixed;
      right: 1.25rem;
      bottom: 1.25rem;
      z-index: 30;
      width: 2.75rem;
      height: 2.75rem;
      border-radius: 50%;
      border: 0;
      font: inherit;
      font-size: 1.25rem;
      font-weight: 700;
      color: var(--gc-on-primary);
      background: var(--gc-primary);
      box-shadow: 0 2px 8px rgb(0 0 0 / 25%);
      cursor: pointer;
    }
    .backdrop {
      position: fixed;
      inset: 0;
      z-index: 40;
      background: rgb(0 0 0 / 25%);
    }
    .drawer {
      position: fixed;
      top: 0;
      right: 0;
      bottom: 0;
      z-index: 50;
      width: min(460px, 100vw);
      overflow-y: auto;
      display: grid;
      align-content: start;
      gap: 1rem;
      padding: 1rem 1.25rem 2rem;
      background: var(--gc-surface);
      box-shadow: -4px 0 16px rgb(0 0 0 / 20%);
    }
    .drawer-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
    }
    .close {
      font: inherit;
      padding: 0.25rem 0.75rem;
      cursor: pointer;
    }
    @media print {
      .help-button,
      .backdrop,
      .drawer {
        display: none;
      }
    }
  `,
})
export class ContextHelp {
  private readonly router = inject(Router);
  private readonly trigger = viewChild<ElementRef<HTMLButtonElement>>('trigger');
  private readonly drawer = viewChild<ElementRef<HTMLElement>>('drawer');

  private readonly url = toSignal(
    this.router.events.pipe(
      filter((event) => event instanceof NavigationEnd),
      map((event) => event.urlAfterRedirects),
    ),
    { initialValue: this.router.url },
  );
  protected readonly sheet = computed(() => {
    const id = helpForUrl(this.url());
    return id ? (HELP_SHEETS_BY_ID[id] ?? null) : null;
  });
  protected readonly open = signal(false);

  constructor() {
    // Une navigation (lien du tiroir, recherche) referme le tiroir.
    this.router.events
      .pipe(
        filter((event) => event instanceof NavigationEnd),
        takeUntilDestroyed(),
      )
      .subscribe(() => this.open.set(false));
  }

  @HostListener('document:keydown.escape')
  protected onEscape(): void {
    if (this.open()) {
      this.hide();
    }
  }

  protected show(): void {
    this.open.set(true);
    // Focus sur le titre de la fiche, une fois le tiroir rendu.
    setTimeout(() => this.drawer()?.nativeElement.querySelector<HTMLElement>('h2')?.focus());
  }

  protected hide(): void {
    this.open.set(false);
    setTimeout(() => this.trigger()?.nativeElement.focus());
  }
}

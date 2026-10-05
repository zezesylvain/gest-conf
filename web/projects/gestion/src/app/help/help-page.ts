import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  DOCUMENT,
  ElementRef,
  inject,
  input,
  OnDestroy,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import { SCREENS } from '../core/navigation';
import { HELP_PROFILES, HELP_SHEETS, HELP_SHEETS_BY_ID, TRANSVERSAL } from './help-sheets';
import { HelpSheetView } from './help-sheet';

/**
 * Guide de la gestion, `/aide` (plan L2 §2.3, compétence `guide-utilisateur-integre-angular`) :
 * sommaire suiveur, index par profil et par écran, toutes les fiches, impression. Tout est
 * **dérivé** de `HELP_SHEETS` et de la table des écrans : aucun index saisi à la main.
 */
@Component({
  selector: 'gestion-help-page',
  imports: [RouterLink, TranslatePipe, HelpSheetView],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="guide">
      <nav class="toc" [attr.aria-label]="'gestion.help.toc' | translate">
        <p class="toc-title">{{ 'gestion.help.toc' | translate }}</p>
        <ul>
          @for (item of toc; track item.id) {
            <li>
              <a
                [href]="'#' + item.id"
                [class.active]="active() === item.id"
                [attr.aria-current]="active() === item.id ? 'location' : null"
                (click)="scrollTo($event, item.id)"
                >{{ item.label | translate }}</a
              >
            </li>
          }
        </ul>
      </nav>

      <div class="content">
        <header class="intro">
          <h1>{{ 'gestion.help.title' | translate }}</h1>
          <p>{{ 'gestion.help.lead' | translate }}</p>
          <div class="actions">
            <a routerLink="/">{{ 'gestion.help.back' | translate }}</a>
            <button type="button" class="print" (click)="print()">
              {{ 'gestion.help.print' | translate }}
            </button>
          </div>
        </header>

        <section id="index-profils" class="index" aria-labelledby="index-profils-titre">
          <h2 id="index-profils-titre">{{ 'gestion.help.byProfile' | translate }}</h2>
          @for (group of byProfile; track group.role) {
            <h3>{{ 'gestion.roles.' + group.role | translate }}</h3>
            <ul>
              @for (item of group.sheets; track item.id) {
                <li>
                  <a [href]="'#fiche-' + item.id" (click)="scrollTo($event, 'fiche-' + item.id)">{{
                    item.title | translate
                  }}</a>
                </li>
              }
            </ul>
          }
        </section>

        <section id="index-ecrans" class="index" aria-labelledby="index-ecrans-titre">
          <h2 id="index-ecrans-titre">{{ 'gestion.help.byScreen' | translate }}</h2>
          <ul>
            @for (screen of byScreen; track screen.key) {
              <li>
                {{ screen.label | translate }} :
                <a
                  [href]="'#fiche-' + screen.sheet.id"
                  (click)="scrollTo($event, 'fiche-' + screen.sheet.id)"
                  >{{ screen.sheet.title | translate }}</a
                >
              </li>
            }
          </ul>
          <h3>{{ 'gestion.help.transversal' | translate }}</h3>
          <ul>
            @for (item of transversal; track item.id) {
              <li>
                <a [href]="'#fiche-' + item.id" (click)="scrollTo($event, 'fiche-' + item.id)">{{
                  item.title | translate
                }}</a>
              </li>
            }
          </ul>
        </section>

        @for (item of sheets; track item.id) {
          <section class="sheet-section">
            <gestion-help-sheet [sheet]="item" [anchor]="true" />
          </section>
        }
      </div>
    </div>
  `,
  styles: `
    .guide {
      display: grid;
      grid-template-columns: minmax(12rem, 16rem) minmax(0, 48rem);
      gap: 2rem;
    }
    .toc {
      position: sticky;
      top: 1rem;
      align-self: start;
      max-height: calc(100vh - 2rem);
      overflow-y: auto;
    }
    .toc-title {
      margin: 0 0 0.5rem;
      font-weight: 700;
    }
    .toc ul {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 0.125rem;
    }
    .toc a {
      display: block;
      padding: 0.25rem 0.5rem;
      border-left: 3px solid transparent;
      color: var(--gc-primary);
    }
    .toc a.active {
      border-left-color: var(--gc-primary);
      font-weight: 700;
      background: var(--gc-surface-muted);
    }
    .content {
      display: grid;
      gap: 2rem;
    }
    .intro {
      display: grid;
      gap: 0.5rem;
    }
    h1 {
      margin: 0;
    }
    .intro p {
      margin: 0;
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 1rem;
      align-items: center;
    }
    .print {
      font: inherit;
      padding: 0.3rem 0.75rem;
      cursor: pointer;
    }
    .index,
    .sheet-section {
      scroll-margin-top: 1.5rem;
    }
    .index h2 {
      margin: 0 0 0.5rem;
      font-size: 1.25rem;
    }
    .index h3 {
      margin: 0.75rem 0 0.25rem;
      font-size: 1rem;
    }
    .index ul {
      margin: 0;
      padding-left: 1.25rem;
    }
    .sheet-section {
      padding-top: 1.5rem;
      border-top: 1px solid var(--gc-border);
    }
    @media (max-width: 48rem) {
      .guide {
        grid-template-columns: 1fr;
      }
      .toc {
        position: static;
        max-height: none;
      }
    }
    @media print {
      .toc,
      .actions {
        display: none;
      }
      .guide {
        display: block;
      }
      .toc a.active {
        background: transparent;
      }
    }
  `,
})
export class HelpPage implements OnDestroy {
  /** `?fiche=<id>` : ouverture du guide sur une fiche (lien du tiroir « ? »). */
  readonly fiche = input<string | undefined>();

  private readonly document = inject(DOCUMENT);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private observer: IntersectionObserver | null = null;

  protected readonly sheets = HELP_SHEETS;
  protected readonly byProfile = HELP_PROFILES.map((role) => ({
    role,
    sheets: HELP_SHEETS.filter((item) => item.profiles.includes(role)),
  }));
  protected readonly byScreen = SCREENS.filter((screen) => !screen.path.startsWith('/')).map(
    (screen) => ({ key: screen.key, label: screen.label, sheet: HELP_SHEETS_BY_ID[screen.help] }),
  );
  protected readonly transversal = TRANSVERSAL.map((id) => HELP_SHEETS_BY_ID[id]);
  protected readonly toc = [
    { id: 'index-profils', label: 'gestion.help.byProfile' },
    { id: 'index-ecrans', label: 'gestion.help.byScreen' },
    ...HELP_SHEETS.map((item) => ({ id: `fiche-${item.id}`, label: item.title })),
  ];
  protected readonly active = signal<string>('index-profils');

  constructor() {
    afterNextRender(() => {
      this.observe();
      const target = this.fiche();
      if (target && HELP_SHEETS_BY_ID[target]) {
        this.reveal(`fiche-${target}`);
      }
    });
  }

  ngOnDestroy(): void {
    this.observer?.disconnect();
  }

  /** Défilement sans écrire dans l'historique (« Précédent » ne remonte pas section par section). */
  protected scrollTo(event: Event, id: string): void {
    event.preventDefault();
    this.reveal(id);
  }

  protected print(): void {
    this.document.defaultView?.print();
  }

  private reveal(id: string): void {
    const element = this.document.getElementById(id);
    if (element) {
      element.scrollIntoView({ block: 'start' });
      this.active.set(id);
    }
  }

  /** Sommaire suiveur ; la marge basse négative évite deux sections actives à la fois. */
  private observe(): void {
    const view = this.document.defaultView;
    if (!view || !('IntersectionObserver' in view)) {
      return;
    }
    this.observer = new view.IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            this.active.set((entry.target as HTMLElement).id);
          }
        }
      },
      { rootMargin: '-10% 0px -70% 0px' },
    );
    for (const item of this.toc) {
      const element = this.host.nativeElement.querySelector(`#${item.id}`);
      if (element) {
        this.observer.observe(element);
      }
    }
  }
}

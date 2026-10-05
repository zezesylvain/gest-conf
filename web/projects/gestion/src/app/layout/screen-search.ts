import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DOCUMENT,
  ElementRef,
  HostListener,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { Router } from '@angular/router';
import { LanguageService } from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { NavEntry } from '../core/navigation';
import { NavigationStore } from '../core/navigation-store';
import { search, SearchItem } from '../core/search';

interface Candidate extends SearchItem {
  entry: NavEntry;
}

/**
 * Recherche d'écran de la barre haute (plan L2 §2.3, compétence `recherche-menu-topbar-angular`).
 * Le catalogue est **dérivé du rail** (`NavigationStore.entries`) : il ne relit ni les rôles
 * ni les capacités. Combobox ARIA écrite à la main ; `⌘K` / `Ctrl+K` depuis tout écran.
 */
@Component({
  selector: 'gestion-screen-search',
  imports: [TranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="search">
      <label class="visually-hidden" for="screen-search">
        {{ 'gestion.search.label' | translate }}
      </label>
      <input
        #input
        id="screen-search"
        type="search"
        role="combobox"
        autocomplete="off"
        aria-autocomplete="list"
        aria-controls="screen-search-list"
        aria-describedby="screen-search-hint"
        [attr.aria-expanded]="open()"
        [attr.aria-activedescendant]="activeId()"
        [placeholder]="'gestion.search.placeholder' | translate"
        [value]="query()"
        (input)="onInput($any($event.target).value)"
        (focus)="open.set(true)"
        (blur)="open.set(false)"
        (keydown)="onKeydown($event)"
      />
      <span id="screen-search-hint" class="visually-hidden">
        {{ 'gestion.search.hint' | translate }}
      </span>
      <ul id="screen-search-list" role="listbox" [hidden]="!open()">
        @for (result of results(); track result.entry.key; let i = $index) {
          <!-- mousedown et non click : le blur du champ refermerait la liste avant le clic. -->
          <li
            role="option"
            [id]="'screen-search-option-' + i"
            [attr.aria-selected]="i === highlight()"
            [class.highlighted]="i === highlight()"
            (mousedown)="choose($event, result.entry)"
          >
            <span class="title">{{ result.title }}</span>
            <span class="group">{{ result.group }}</span>
          </li>
        } @empty {
          <li class="empty" role="presentation">
            {{
              (query().trim().length < 2 ? 'gestion.search.tooShort' : 'gestion.search.none')
                | translate
            }}
          </li>
        }
      </ul>
    </div>
  `,
  styles: `
    :host {
      display: block;
      flex: 1 1 14rem;
      max-width: 24rem;
      min-width: 10rem;
    }
    .search {
      position: relative;
    }
    input {
      width: 100%;
      font: inherit;
      padding: 0.3rem 0.6rem;
      border: 1px solid transparent;
      border-radius: 0.25rem;
      background: var(--gc-surface);
      color: var(--gc-text);
    }
    ul {
      position: absolute;
      z-index: 20;
      top: calc(100% + 0.25rem);
      left: 0;
      right: 0;
      margin: 0;
      padding: 0.25rem;
      list-style: none;
      max-height: 22rem;
      overflow-y: auto;
      background: var(--gc-surface);
      color: var(--gc-text);
      border: 1px solid var(--gc-border);
      border-radius: 0.25rem;
      box-shadow: 0 4px 16px rgb(0 0 0 / 15%);
    }
    li {
      display: flex;
      justify-content: space-between;
      gap: 0.75rem;
      padding: 0.35rem 0.5rem;
      border-radius: 0.25rem;
      cursor: pointer;
    }
    li.highlighted {
      background: var(--gc-surface-muted);
      outline: 2px solid var(--gc-primary);
      outline-offset: -2px;
    }
    .group {
      color: var(--gc-muted);
      font-size: 0.85rem;
      white-space: nowrap;
    }
    .empty {
      color: var(--gc-muted);
      cursor: default;
    }
  `,
})
export class ScreenSearch {
  private readonly navigation = inject(NavigationStore);
  private readonly translate = inject(TranslateService);
  private readonly language = inject(LanguageService);
  private readonly router = inject(Router);
  private readonly document = inject(DOCUMENT);
  private readonly input = viewChild.required<ElementRef<HTMLInputElement>>('input');

  protected readonly query = signal('');
  protected readonly open = signal(false);
  protected readonly highlight = signal(0);

  /** Catalogue traduit, recalculé au changement de langue ou de rail. */
  private readonly candidates = computed<Candidate[]>(() => {
    this.language.current();
    return this.navigation.entries().map((entry) => ({
      entry,
      title: this.translate.instant(entry.label),
      keywords: String(this.translate.instant(entry.keywords))
        .split(',')
        .map((word) => word.trim())
        .filter(Boolean),
      group: this.translate.instant(`gestion.nav.groups.${entry.group}`),
      order: entry.order,
    }));
  });
  protected readonly results = computed(() => search(this.candidates(), this.query()));
  protected readonly activeId = computed(() =>
    this.open() && this.results().length ? `screen-search-option-${this.highlight()}` : null,
  );

  /** `⌘K` / `Ctrl+K` : focus et sélection du champ, depuis n'importe quel écran. */
  @HostListener('document:keydown', ['$event'])
  protected onShortcut(event: KeyboardEvent): void {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      const element = this.input().nativeElement;
      element.focus();
      element.select();
    }
  }

  protected onInput(value: string): void {
    this.query.set(value);
    // Réinitialisé ici, à l'événement, et non dans un effect : Entrée ouvrirait sinon le
    // résultat surligné de la saisie précédente.
    this.highlight.set(0);
    this.open.set(true);
  }

  protected onKeydown(event: KeyboardEvent): void {
    const count = this.results().length;
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        this.open.set(true);
        if (count) this.highlight.set((this.highlight() + 1) % count);
        break;
      case 'ArrowUp':
        event.preventDefault();
        this.open.set(true);
        if (count) this.highlight.set((this.highlight() - 1 + count) % count);
        break;
      case 'Enter': {
        const result = this.results()[this.highlight()];
        if (result) {
          event.preventDefault();
          this.go(result.entry);
        }
        break;
      }
      case 'Escape':
        event.preventDefault();
        this.reset();
        this.input().nativeElement.blur();
        this.document.getElementById('contenu')?.focus();
        break;
    }
  }

  protected choose(event: MouseEvent, entry: NavEntry): void {
    event.preventDefault();
    this.go(entry);
  }

  private go(entry: NavEntry): void {
    this.reset();
    this.input().nativeElement.blur();
    void this.router.navigateByUrl(entry.url);
  }

  private reset(): void {
    this.query.set('');
    this.highlight.set(0);
    this.open.set(false);
  }
}

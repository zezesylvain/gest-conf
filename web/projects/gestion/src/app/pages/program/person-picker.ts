import {
  ChangeDetectionStrategy,
  Component,
  inject,
  input,
  OnDestroy,
  output,
  signal,
} from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { PersonSearch } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

import { ProgramApi } from '../../core/program-api';

/**
 * Choix d'une personne de l'édition (rôles de séance, intervenants invités, I10 et I11) :
 * recherche par nom, résultats en boutons, jamais d'adresse (le serveur n'en renvoie pas).
 * Une personne absente de l'édition s'invite d'abord (rôles `SESSION_CHAIR`, `SPEAKER`).
 */
@Component({
  selector: 'gestion-person-picker',
  imports: [TranslatePipe, MatButtonModule, MatFormFieldModule, MatInputModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (chosen(); as person) {
      <p class="chosen">
        {{ 'gestion.program.people.chosen' | translate: { name: person.name } }}
        <button mat-button type="button" (click)="clear()">
          {{ 'gestion.program.people.change' | translate }}
        </button>
      </p>
    } @else {
      <mat-form-field appearance="outline" subscriptSizing="dynamic">
        <mat-label>{{ label() | translate }}</mat-label>
        <input matInput type="search" (input)="search($any($event.target).value)" />
        <mat-hint>{{ 'gestion.program.people.hint' | translate }}</mat-hint>
      </mat-form-field>
      <div aria-live="polite">
        @if (searched() && !results().length) {
          <p class="muted">{{ 'gestion.program.people.none' | translate }}</p>
        }
      </div>
      @if (results().length) {
        <ul class="results">
          @for (person of results(); track person.id) {
            <li>
              <button mat-stroked-button type="button" (click)="choose(person)">
                {{ person.name }}
                @if (person.institution) {
                  <span class="muted">— {{ person.institution }}</span>
                }
              </button>
            </li>
          }
        </ul>
      }
    }
  `,
  styles: `
    .results {
      list-style: none;
      margin: 0.25rem 0 0;
      padding: 0;
      display: grid;
      gap: 0.25rem;
    }
    .chosen {
      margin: 0;
    }
    .muted {
      color: var(--gc-muted);
    }
    mat-form-field {
      width: 100%;
    }
  `,
})
export class PersonPicker implements OnDestroy {
  readonly editionId = input.required<number>();
  readonly label = input('gestion.program.people.search');
  readonly picked = output<PersonSearch | null>();

  private readonly api = inject(ProgramApi);
  protected readonly results = signal<PersonSearch[]>([]);
  protected readonly searched = signal(false);
  protected readonly chosen = signal<PersonSearch | null>(null);
  private timer: ReturnType<typeof setTimeout> | null = null;
  private sequence = 0;

  ngOnDestroy(): void {
    if (this.timer) {
      clearTimeout(this.timer);
    }
  }

  /** Recherche différée (300 ms) ; seule la réponse la plus récente compte. */
  protected search(value: string): void {
    if (this.timer) {
      clearTimeout(this.timer);
    }
    const query = value.trim();
    if (query.length < 2) {
      this.results.set([]);
      this.searched.set(false);
      return;
    }
    this.timer = setTimeout(() => void this.run(query), 300);
  }

  async run(query: string): Promise<void> {
    const sequence = ++this.sequence;
    try {
      const people = await this.api.people(this.editionId(), query);
      if (sequence === this.sequence) {
        this.results.set(people);
        this.searched.set(true);
      }
    } catch {
      if (sequence === this.sequence) {
        this.results.set([]);
        this.searched.set(true);
      }
    }
  }

  protected choose(person: PersonSearch): void {
    this.chosen.set(person);
    this.results.set([]);
    this.picked.emit(person);
  }

  clear(): void {
    this.chosen.set(null);
    this.searched.set(false);
    this.picked.emit(null);
  }
}

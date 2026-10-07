import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  OnInit,
  signal,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import {
  ErrorSummary,
  LanguageService,
  MeStore,
  PageHeader,
  Task,
  TaskPerson,
  TaskPriority,
  TaskStatus,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { OrganisationApi } from '../../core/organisation-api';
import { editionCapabilities, errorMessages } from '../../core/page-support';
import { TASK_PRIORITIES, TASK_STATUSES, formatDay, isStale } from './organisation-support';

/**
 * Tâches du CO en tableau à trois colonnes (plan L8, N3 ; `tasks.read`, écriture
 * `tasks.write`). Pas de glisser-déposer : chaque carte se déplace par une liste « Déplacer
 * vers » accessible au clavier, annoncée aux lecteurs d'écran. Chaque écriture porte la
 * révision lue ; une tâche modifiée entre-temps est rechargée (412).
 */
@Component({
  selector: 'gestion-tasks-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './tasks-page.html',
  styleUrl: '../page.scss',
  styles: `
    .board {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
      gap: 1rem;
      align-items: start;
    }
    .column {
      border: 1px solid var(--gc-border);
      border-radius: 0.5rem;
      padding: 0.75rem;
    }
    .column h2 {
      margin-top: 0;
      font-size: 1.1rem;
    }
    .column ul {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 0.75rem;
    }
    .task {
      border: 1px solid var(--gc-border);
      border-radius: 0.5rem;
      padding: 0.6rem 0.75rem;
      background: var(--gc-surface, transparent);
    }
    .task h3 {
      margin: 0 0 0.25rem;
      font-size: 1rem;
    }
    .meta {
      margin: 0.25rem 0;
      font-size: 0.875rem;
    }
    .late {
      font-weight: 600;
    }
    .filters {
      display: flex;
      flex-wrap: wrap;
      gap: 1rem;
      align-items: center;
    }
    select {
      font: inherit;
      padding: 0.25rem;
    }
  `,
})
export class TasksPage implements OnInit {
  readonly editionId = input.required<string>();

  private readonly api = inject(OrganisationApi);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly statuses = TASK_STATUSES;
  protected readonly priorities = TASK_PRIORITIES;
  protected readonly tasks = signal<Task[]>([]);
  protected readonly members = signal<TaskPerson[]>([]);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly mine = signal(false);
  protected readonly archived = signal(false);
  protected readonly canWrite = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('tasks.write'),
  );
  protected readonly columns = computed(() =>
    this.statuses.map((status) => ({
      status,
      tasks: this.tasks()
        .filter((task) => task.status === status)
        .sort((a, b) => a.position - b.position || a.id - b.id),
    })),
  );

  protected readonly form = inject(NonNullableFormBuilder).group({
    title: ['', [Validators.required, Validators.maxLength(200)]],
    assignee: [null as number | null],
    due_date: [''],
    priority: ['normal' as TaskPriority],
    label: ['', Validators.maxLength(50)],
  });

  async ngOnInit(): Promise<void> {
    await Promise.all([this.reload(), this.loadMembers()]);
    this.loading.set(false);
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected day(value: string | null): string {
    return formatDay(value, this.language.current());
  }

  protected async toggleMine(checked: boolean): Promise<void> {
    this.mine.set(checked);
    await this.reload();
  }

  protected async toggleArchived(checked: boolean): Promise<void> {
    this.archived.set(checked);
    await this.reload();
  }

  protected async create(): Promise<void> {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    await this.run(async () => {
      const task = await this.api.createTask(this.edition(), {
        title: value.title.trim(),
        assignee: value.assignee,
        due_date: value.due_date || null,
        priority: value.priority,
        label: value.label.trim(),
      });
      this.form.reset({ priority: 'normal', assignee: null });
      this.status.set(this.translate.instant('gestion.tasks.created', { title: task.title }));
    });
  }

  /** Déplacement d'une carte (liste « Déplacer vers », sans glisser-déposer). */
  protected async move(task: Task, to: string): Promise<void> {
    if (!TASK_STATUSES.includes(to as TaskStatus) || to === task.status) return;
    await this.run(async () => {
      await this.api.updateTask(this.edition(), task.id, task.revision, {
        status: to as TaskStatus,
      });
      this.status.set(
        this.translate.instant('gestion.tasks.moved', {
          title: task.title,
          column: this.translate.instant(`gestion.tasks.status.${to}`),
        }),
      );
    });
  }

  private async run(action: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      await action();
    } catch (error) {
      this.errors.set(
        isStale(error)
          ? [this.translate.instant('gestion.tasks.stale')]
          : errorMessages(this.translate, error, this.form),
      );
    } finally {
      this.busy.set(false);
      await this.reload();
    }
  }

  private async reload(): Promise<void> {
    try {
      this.tasks.set(
        await this.api.tasks(this.edition(), {
          mine: this.mine() || undefined,
          archived: this.archived() || undefined,
        }),
      );
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }

  private async loadMembers(): Promise<void> {
    try {
      this.members.set(await this.api.members(this.edition()));
    } catch {
      this.members.set([]);
    }
  }
}

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
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import {
  ErrorSummary,
  formatInZone,
  LanguageService,
  MeStore,
  PageHeader,
  TaskAttachment,
  TaskDetail,
  TaskPerson,
  TaskPriority,
  TaskStatus,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { OrganisationApi } from '../../core/organisation-api';
import { editionCapabilities, errorMessages } from '../../core/page-support';
import { saveBlob } from '../../core/registrations-api';
import { confirmAction } from '../events/events-support';
import {
  ATTACHMENT_ACCEPT,
  ATTACHMENT_MAX_BYTES,
  TASK_PRIORITIES,
  TASK_STATUSES,
  isStale,
} from './organisation-support';

/**
 * Fiche d'une tâche (plan L8, N3) : champs, commentaires, pièces jointes (PDF, PNG, JPEG,
 * 10 Mo, type vérifié par le serveur), archivage. Écriture `tasks.write`, avec la révision
 * lue (`If-Match`) : si la tâche a changé entre-temps, la fiche est rechargée et le
 * message le dit.
 */
@Component({
  selector: 'gestion-task-detail-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    TranslatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './task-detail-page.html',
  styleUrl: '../page.scss',
})
export class TaskDetailPage implements OnInit {
  readonly editionId = input.required<string>();
  readonly taskId = input.required<string>();

  private readonly api = inject(OrganisationApi);
  private readonly dialog = inject(MatDialog);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  protected readonly language = inject(LanguageService);

  protected readonly statuses = TASK_STATUSES;
  protected readonly priorities = TASK_PRIORITIES;
  protected readonly accept = ATTACHMENT_ACCEPT;
  protected readonly task = signal<TaskDetail | null>(null);
  protected readonly members = signal<TaskPerson[]>([]);
  protected readonly loading = signal(true);
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly status = signal('');
  protected readonly canWrite = computed(() =>
    editionCapabilities(this.meStore, this.editionId()).includes('tasks.write'),
  );

  private readonly fb = inject(NonNullableFormBuilder);
  protected readonly form = this.fb.group({
    title: ['', [Validators.required, Validators.maxLength(200)]],
    description: ['', Validators.maxLength(5000)],
    status: ['todo' as TaskStatus],
    assignee: [null as number | null],
    due_date: [''],
    priority: ['normal' as TaskPriority],
    label: ['', Validators.maxLength(50)],
  });
  protected readonly commentForm = this.fb.group({
    body: ['', [Validators.required, Validators.maxLength(2000)]],
  });

  async ngOnInit(): Promise<void> {
    await Promise.all([this.reload(), this.loadMembers()]);
    this.loading.set(false);
  }

  private edition(): number {
    return Number(this.editionId());
  }

  private id(): number {
    return Number(this.taskId());
  }

  protected date(value: string): string {
    return formatInZone(value, undefined, this.language.current());
  }

  protected size(bytes: number): string {
    return `${Math.max(1, Math.round(bytes / 1024))} ko`;
  }

  protected async save(): Promise<void> {
    const task = this.task();
    if (!task || this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const value = this.form.getRawValue();
    await this.run('gestion.tasks.detail.saved', () =>
      this.api.updateTask(this.edition(), task.id, task.revision, {
        title: value.title.trim(),
        description: value.description,
        status: value.status,
        assignee: value.assignee,
        due_date: value.due_date || null,
        priority: value.priority,
        label: value.label.trim(),
      }),
    );
  }

  protected async archive(): Promise<void> {
    const task = this.task();
    if (!task) return;
    const answer = await confirmAction(
      this.dialog,
      this.translate,
      'gestion.tasks.detail.archive',
      {
        title: task.title,
      },
    );
    if (!answer) return;
    await this.run('gestion.tasks.detail.archived', () =>
      this.api.archiveTask(this.edition(), task.id, task.revision),
    );
  }

  protected async restore(): Promise<void> {
    const task = this.task();
    if (!task) return;
    await this.run('gestion.tasks.detail.restored', () =>
      this.api.restoreTask(this.edition(), task.id, task.revision),
    );
  }

  protected async addComment(): Promise<void> {
    const task = this.task();
    if (!task || this.commentForm.invalid) {
      this.commentForm.markAllAsTouched();
      return;
    }
    const body = this.commentForm.getRawValue().body.trim();
    await this.run('gestion.tasks.detail.commented', async () => {
      const updated = await this.api.comment(this.edition(), task.id, body);
      this.commentForm.reset();
      return updated;
    });
  }

  protected async upload(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    const task = this.task();
    if (!file || !task) return;
    if (file.size > ATTACHMENT_MAX_BYTES) {
      this.errors.set([this.translate.instant('gestion.tasks.detail.tooLarge')]);
      return;
    }
    await this.run('gestion.tasks.detail.uploaded', () =>
      this.api.uploadAttachment(this.edition(), task.id, file),
    );
  }

  protected async download(attachment: TaskAttachment): Promise<void> {
    const task = this.task();
    if (!task) return;
    try {
      saveBlob(
        await this.api.downloadAttachment(this.edition(), task.id, attachment.id),
        attachment.name,
      );
    } catch (error) {
      this.errors.set(errorMessages(this.translate, error));
    }
  }

  protected async removeAttachment(attachment: TaskAttachment): Promise<void> {
    const task = this.task();
    if (!task) return;
    const answer = await confirmAction(
      this.dialog,
      this.translate,
      'gestion.tasks.detail.removeAttachment',
      { name: attachment.name },
    );
    if (!answer) return;
    await this.run('gestion.tasks.detail.removed', () =>
      this.api.removeAttachment(this.edition(), task.id, attachment.id),
    );
  }

  private async run(message: string, action: () => Promise<TaskDetail>): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.status.set('');
    try {
      this.show(await action());
      this.status.set(this.translate.instant(message));
    } catch (error) {
      if (isStale(error)) {
        this.errors.set([this.translate.instant('gestion.tasks.stale')]);
        await this.reload();
      } else {
        // Erreurs de champ du serveur au résumé : ce formulaire n'en affiche pas sous ses champs.
        this.errors.set(errorMessages(this.translate, error));
      }
    } finally {
      this.busy.set(false);
    }
  }

  private show(task: TaskDetail): void {
    this.task.set(task);
    this.form.reset({
      title: task.title,
      description: task.description,
      status: task.status,
      assignee: task.assignee?.id ?? null,
      due_date: task.due_date ?? '',
      priority: task.priority,
      label: task.label,
    });
    if (!this.canWrite() || task.archived_at) {
      this.form.disable();
    } else {
      this.form.enable();
    }
  }

  private async reload(): Promise<void> {
    try {
      this.show(await this.api.task(this.edition(), this.id()));
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

import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  DOCUMENT,
  ElementRef,
  inject,
  input,
  OnDestroy,
  OnInit,
  signal,
  viewChild,
} from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import {
  CheckinSummary,
  ErrorSummary,
  formatInZone,
  LanguageService,
  MeStore,
  PageHeader,
} from '@gestconf/shared';
import { TranslatePipe, TranslateService } from '@ngx-translate/core';

import { CheckinDesk, DeskResult } from '../../core/checkin-desk';
import { EventsApi } from '../../core/events-api';
import { editionCapabilities, errorMessages } from '../../core/page-support';
import { QrScanner } from '../../core/qr-scanner';
import { isUnreachable, ReceptionInstaller } from '../../core/reception';
import {
  deviceName,
  outcomeTone,
  rememberDeviceName,
  saveSession,
  saveSessions,
  savedSession,
  savedSessions,
  SessionChoice,
  title,
} from './events-support';

/**
 * Accueil du jour J (plan L7, K4 à K7) : lecture du QR des badges par la caméra, saisie de
 * la référence en secours (`checkin.manage`), mode « session » pour émarger l'entrée d'une
 * session publiée. **En ligne d'abord** ; sans réseau, décision sur la liste téléchargée et
 * file de pointages, synchronisée au retour du réseau. Écran installable (manifeste et
 * service worker enregistrés d'ici seulement, bilan de L7.0).
 */
@Component({
  selector: 'gestion-reception-page',
  imports: [
    ReactiveFormsModule,
    TranslatePipe,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    ErrorSummary,
    PageHeader,
  ],
  providers: [CheckinDesk],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './reception-page.html',
  styleUrls: ['../page.scss', './reception-page.scss'],
})
export class ReceptionPage implements OnInit, OnDestroy {
  readonly editionId = input.required<string>();
  /** `?session=` : ouvert depuis les sessions du jour, en mode « session » (K7). */
  readonly session = input<string>();

  protected readonly desk = inject(CheckinDesk);
  private readonly api = inject(EventsApi);
  private readonly installer = inject(ReceptionInstaller);
  private readonly meStore = inject(MeStore);
  private readonly translate = inject(TranslateService);
  private readonly document = inject(DOCUMENT);
  protected readonly language = inject(LanguageService);

  private readonly video = viewChild.required<ElementRef<HTMLVideoElement>>('video');
  private readonly canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('canvas');
  private scanner: QrScanner | null = null;

  protected readonly online = signal(this.document.defaultView?.navigator.onLine ?? true);
  protected readonly camera = signal(false);
  protected readonly cameraError = signal('');
  protected readonly busy = signal(false);
  protected readonly errors = signal<string[]>([]);
  protected readonly notice = signal('');
  protected readonly result = signal<DeskResult | null>(null);
  protected readonly summary = signal<CheckinSummary | null>(null);
  protected readonly sessions = signal<SessionChoice[]>([]);
  protected readonly device = signal(deviceName());
  private readonly capabilities = computed(() =>
    editionCapabilities(this.meStore, this.editionId()),
  );
  protected readonly canEnter = computed(() => this.capabilities().includes('checkin.manage'));
  /**
   * Pointage d'accueil et liste hors ligne : `checkin.scan`. Le président de séance seul
   * émarge ses sessions, en ligne (K7). Démarré hors ligne, `/me` est inconnu : la liste de
   * l'appareil fait foi jusqu'à la synchronisation.
   */
  protected readonly canScanReception = computed(
    () => !this.meStore.loaded() || this.capabilities().includes('checkin.scan'),
  );
  protected readonly sessionTitle = computed(() => {
    const id = this.desk.session();
    const found = this.sessions().find((item) => item.id === id);
    return found ? title(found, this.language.current()) : '';
  });
  protected readonly manualForm = inject(NonNullableFormBuilder).group({
    reference: ['', [Validators.required, Validators.maxLength(32)]],
  });

  constructor() {
    const window = this.document.defaultView;
    const update = () => {
      const online = window?.navigator.onLine ?? true;
      this.online.set(online);
      if (online && this.desk.queue().length) {
        void this.synchronize();
      }
    };
    window?.addEventListener('online', update);
    window?.addEventListener('offline', update);
    inject(DestroyRef).onDestroy(() => {
      window?.removeEventListener('online', update);
      window?.removeEventListener('offline', update);
    });
  }

  async ngOnInit(): Promise<void> {
    const id = this.edition();
    void this.installer.install();
    try {
      await this.desk.init(id);
    } catch {
      // IndexedDB indisponible : l'accueil reste utilisable en ligne.
    }
    this.sessions.set(savedSessions(id));
    const session = Number(this.session()) || savedSession(id);
    if (session !== null && this.sessions().some((item) => item.id === session)) {
      this.desk.session.set(session);
    }
    if (this.online()) {
      await Promise.all([
        this.canScanReception() ? this.loadSummary() : Promise.resolve(),
        this.loadSessions(Number(this.session()) || null),
      ]);
      if (this.desk.queue().length) {
        await this.synchronize();
      }
    }
  }

  ngOnDestroy(): void {
    this.scanner?.stop();
  }

  private edition(): number {
    return Number(this.editionId());
  }

  protected date(value: string): string {
    return formatInZone(value, undefined, this.language.current());
  }

  protected tone(result: DeskResult): string {
    return outcomeTone(result.outcome);
  }

  protected label(item: { label_fr: string; label_en: string }): string {
    return (this.language.current() === 'en' && item.label_en) || item.label_fr;
  }

  protected sessionLabel(item: SessionChoice): string {
    return `${this.date(item.starts_at)} · ${title(item, this.language.current())}`;
  }

  /** Mode : une session (son identifiant), ou l'accueil (`null`, option de valeur 0). */
  protected selectSession(value: number | null): void {
    this.desk.session.set(value);
    saveSession(this.edition(), value);
    this.result.set(null);
  }

  protected renameDevice(value: string): void {
    rememberDeviceName(value);
    this.device.set(deviceName());
  }

  protected async download(): Promise<void> {
    await this.run(async () => {
      const bundle = await this.desk.download();
      this.notice.set(
        this.translate.instant('gestion.reception.bundle.downloaded', {
          count: bundle.entries.length,
        }),
      );
    });
  }

  protected async forget(): Promise<void> {
    await this.run(async () => {
      await this.desk.forget();
      this.notice.set(this.translate.instant('gestion.reception.bundle.forgotten'));
    });
  }

  protected async synchronize(): Promise<void> {
    this.errors.set([]);
    try {
      const { sent, rejected } = await this.desk.synchronize(this.device());
      if (sent) {
        this.notice.set(
          this.translate.instant('gestion.reception.queue.synced', { sent, rejected }),
        );
        await this.loadSummary();
      }
    } catch (error) {
      if (isUnreachable(error)) {
        this.online.set(false);
      } else {
        this.errors.set(errorMessages(this.translate, error));
      }
    }
  }

  protected async toggleCamera(): Promise<void> {
    if (this.camera()) {
      this.scanner?.stop();
      this.camera.set(false);
      return;
    }
    this.cameraError.set('');
    this.scanner ??= new QrScanner(
      this.video().nativeElement,
      this.canvas().nativeElement,
      (text) => void this.read(text),
    );
    try {
      await this.scanner.start();
      this.camera.set(true);
    } catch (error) {
      const name = error instanceof DOMException ? error.name : '';
      this.cameraError.set(
        this.translate.instant(
          name === 'NotAllowedError'
            ? 'gestion.reception.camera.denied'
            : 'gestion.reception.camera.unavailable',
        ),
      );
      this.scanner.stop();
    }
  }

  /** Badge lu : texte du QR transmis tel quel (jamais affiché ni journalisé côté client). */
  protected async read(token: string): Promise<void> {
    await this.run(async () => this.show(await this.desk.read(token.trim(), this.device())));
  }

  protected async enter(): Promise<void> {
    if (this.manualForm.invalid) {
      this.manualForm.markAllAsTouched();
      return;
    }
    await this.run(async () => {
      const result = await this.desk.enter(this.manualForm.getRawValue().reference, this.device());
      this.show(result);
      if (result.outcome !== 'bad_reference') {
        this.manualForm.reset();
      }
    });
  }

  protected clearRejected(): void {
    this.desk.clearRejected();
  }

  private show(result: DeskResult): void {
    this.result.set(result);
    const tone = outcomeTone(result.outcome);
    this.document.defaultView?.navigator.vibrate?.(tone === 'ok' ? 80 : [80, 60, 80]);
    if (!result.offline && result.outcome === 'checked_in' && this.desk.session() === null) {
      this.summary.update((value) => value && { ...value, checked_in: value.checked_in + 1 });
    }
  }

  private async loadSummary(): Promise<void> {
    try {
      this.summary.set(await this.api.summary(this.edition()));
    } catch (error) {
      if (isUnreachable(error)) this.online.set(false);
    }
  }

  private async loadSessions(requested: number | null): Promise<void> {
    try {
      const rows = await this.api.daySessions(this.edition());
      const choices = rows.map(({ id, title_fr, title_en, starts_at }) => ({
        id,
        title_fr,
        title_en,
        starts_at,
      }));
      this.sessions.set(choices);
      saveSessions(this.edition(), choices);
      const current = requested ?? this.desk.session();
      if (current !== null && choices.some((item) => item.id === current)) {
        this.selectSession(current);
      } else if (current !== null || !this.canScanReception()) {
        // Session disparue du programme publié ; sans `checkin.scan`, une session s'impose.
        this.selectSession(this.canScanReception() ? null : (choices[0]?.id ?? null));
      }
    } catch (error) {
      if (isUnreachable(error)) this.online.set(false);
    }
  }

  private async run(action: () => Promise<void>): Promise<void> {
    this.busy.set(true);
    this.errors.set([]);
    this.notice.set('');
    try {
      await action();
    } catch (error) {
      if (isUnreachable(error)) {
        this.online.set(false);
      }
      this.errors.set(errorMessages(this.translate, error));
    } finally {
      this.busy.set(false);
    }
  }
}

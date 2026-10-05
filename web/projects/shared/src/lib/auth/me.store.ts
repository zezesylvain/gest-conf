import { computed, inject, Injectable, signal } from '@angular/core';

import { Api } from '../api/api';
import { me } from '../api/fn/me/me';
import { mePreferencesUpdate } from '../api/fn/me/me-preferences-update';
import { Locale } from '../api/models/locale';
import { Me } from '../api/models/me';

/** Compte connecté (`GET /v1/me`), en signaux (plan L1 §10.4). */
@Injectable({ providedIn: 'root' })
export class MeStore {
  private readonly api = inject(Api);
  private readonly meSignal = signal<Me | null>(null);

  readonly me = this.meSignal.asReadonly();
  readonly loaded = computed(() => this.meSignal() !== null);

  async load(): Promise<Me> {
    const value = await this.api.invoke(me);
    this.meSignal.set(value);
    return value;
  }

  set(value: Me): void {
    this.meSignal.set(value);
  }

  /** Langue du compte (interface et e-mails) : `PATCH /v1/me/preferences`. */
  async updateLocale(locale: Locale): Promise<Me> {
    const value = await this.api.invoke(mePreferencesUpdate, { body: { locale } });
    this.meSignal.set(value);
    return value;
  }

  clear(): void {
    this.meSignal.set(null);
  }
}

import { computed, Injectable, signal } from '@angular/core';

import { AllauthUser, AuthResult } from './allauth';

export type SessionState = 'unknown' | 'anonymous' | 'authenticated';

/** État de la session, en signaux (plan L1 §10.4). Aucun jeton n'est stocké. */
@Injectable({ providedIn: 'root' })
export class SessionStore {
  private readonly stateSignal = signal<SessionState>('unknown');
  private readonly userSignal = signal<AllauthUser | null>(null);
  /** Vrai après une expiration constatée (401 sous /api/v1/) : message dédié. */
  private readonly expiredSignal = signal(false);

  readonly state = this.stateSignal.asReadonly();
  readonly user = this.userSignal.asReadonly();
  readonly expired = this.expiredSignal.asReadonly();
  readonly authenticated = computed(() => this.stateSignal() === 'authenticated');

  apply(result: AuthResult): void {
    this.stateSignal.set(result.authenticated ? 'authenticated' : 'anonymous');
    this.userSignal.set(result.authenticated ? result.user : null);
    if (result.authenticated) {
      this.expiredSignal.set(false);
    }
  }

  clear(options: { expired?: boolean } = {}): void {
    this.stateSignal.set('anonymous');
    this.userSignal.set(null);
    this.expiredSignal.set(options.expired ?? false);
  }
}

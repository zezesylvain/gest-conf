import { inject, Injectable, signal } from '@angular/core';
import { Api, meNotifications, meNotificationsRead, NotificationList } from '@gestconf/shared';

/**
 * Cloche de l'espace compte (plan L3, F13). Pas de temps réel (règle n° 9) : le nombre de
 * notifications non lues est relu à l'ouverture de l'espace et à chaque navigation.
 */
@Injectable({ providedIn: 'root' })
export class NotificationsStore {
  private readonly api = inject(Api);

  /** Notifications non lues (toutes, pas seulement celles affichées). */
  readonly unread = signal(0);

  async refresh(): Promise<void> {
    this.unread.set((await this.list()).unread);
  }

  async list(): Promise<NotificationList> {
    const list = await this.api.invoke(meNotifications);
    this.unread.set(list.unread);
    return list;
  }

  /** Marque comme lues les notifications désignées, ou toutes. */
  async markRead(ids?: number[]): Promise<void> {
    const result = await this.api.invoke(meNotificationsRead, {
      body: ids ? { ids } : {},
    });
    this.unread.set(result.unread);
  }
}

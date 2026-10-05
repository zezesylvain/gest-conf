import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { Notification } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { provideAccountTesting } from '../testing';
import { NotificationsPage } from './notifications-page';
import { NotificationsStore } from './notifications.store';

function item(overrides: Partial<Notification>): Notification {
  return {
    id: 1,
    kind: 'submission_received',
    payload: { submission_id: 7, reference: 'GC27-0001', title: 'Étude', edition_code: 'GC27' },
    created_at: '2026-10-05T10:00:00Z',
    read_at: null,
    ...overrides,
  };
}

describe('NotificationsPage', () => {
  let store: {
    unread: ReturnType<typeof vi.fn>;
    list: ReturnType<typeof vi.fn>;
    markRead: ReturnType<typeof vi.fn>;
  };

  async function render(items: Notification[], unread = 1) {
    store = {
      unread: vi.fn(() => unread),
      list: vi.fn().mockResolvedValue({ unread, results: items }),
      markRead: vi.fn().mockResolvedValue(undefined),
    };
    TestBed.configureTestingModule({
      imports: [NotificationsPage],
      providers: [...provideAccountTesting(), { provide: NotificationsStore, useValue: store }],
    });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(NotificationsPage);
    await fixture.whenStable();
    fixture.detectChanges();
    return { fixture, root: fixture.nativeElement as HTMLElement };
  }

  it('texte composé par nature (traductions), non lue signalée, lien vers la soumission', async () => {
    const { root } = await render([
      item({}),
      item({
        id: 2,
        kind: 'coauthor_added',
        payload: { reference: 'GC27-0002', title: 'Autre', edition_code: 'GC27' },
        read_at: '2026-10-05T11:00:00Z',
      }),
      item({
        id: 3,
        kind: 'draft_reminder',
        payload: { submission_id: 9, reference: '', title: '', closes_at: '2026-10-12T23:59:00Z' },
      }),
    ]);
    const rows = Array.from(root.querySelectorAll('li')).map((li) => li.textContent ?? '');
    expect(rows[0]).toContain('Votre soumission GC27-0001 « Étude » a bien été reçue.');
    expect(rows[0]).toContain('Non lue');
    expect(rows[1]).toContain('co-auteur de la soumission GC27-0002');
    expect(rows[1]).not.toContain('Ouvrir'); // co-auteur : aucun accès (F5)
    expect(rows[2]).toContain('(sans titre)');
    expect(rows[2]).toContain('12 oct. 2026');
    expect(root.querySelector('a[href="/compte/soumissions/7"]')).not.toBeNull();
  });

  it('« Tout marquer comme lu » puis relecture', async () => {
    const { fixture, root } = await render([item({})]);
    root.querySelector<HTMLButtonElement>('button')!.click();
    await fixture.whenStable();
    expect(store.markRead).toHaveBeenCalledWith();
    expect(store.list).toHaveBeenCalledTimes(2);
  });

  it('ouvrir une notification non lue la marque comme lue', async () => {
    const { root } = await render([item({})]);
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    root.querySelector<HTMLAnchorElement>('a')!.click();
    expect(store.markRead).toHaveBeenCalledWith([1]);
    expect(navigate).toHaveBeenCalled();
  });

  it('aucune notification', async () => {
    const { root } = await render([], 0);
    expect(root.textContent).toContain('Aucune notification.');
    expect(root.querySelector('button')).toBeNull();
  });
});

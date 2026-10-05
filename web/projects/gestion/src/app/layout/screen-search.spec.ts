import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, Routes } from '@angular/router';
import { MeEdition } from '@gestconf/shared';
import { useTestLanguage } from '@gestconf/shared/testing';

import { CHAIR_EDITION, provideGestionTesting } from '../../testing/gestion-testing';
import { SCREENS } from '../core/navigation';
import { NavigationStore } from '../core/navigation-store';
import { ScreenSearch } from './screen-search';

@Component({ template: '' })
class Blank {}

const ROUTES: Routes = [{ path: '**', component: Blank }];

async function render(edition: MeEdition = CHAIR_EDITION) {
  TestBed.configureTestingModule({
    imports: [ScreenSearch],
    providers: provideGestionTesting([edition], ROUTES),
  });
  await useTestLanguage('fr');
  TestBed.inject(NavigationStore).enterEdition(String(edition.id));
  const fixture = TestBed.createComponent(ScreenSearch);
  await fixture.whenStable();
  const root = fixture.nativeElement as HTMLElement;
  const input = root.querySelector('input')!;
  const router = TestBed.inject(Router);
  const navigate = vi.spyOn(router, 'navigateByUrl');
  const type = async (value: string) => {
    input.dispatchEvent(new Event('focus'));
    input.value = value;
    input.dispatchEvent(new Event('input'));
    await fixture.whenStable();
  };
  const key = async (name: string, init: KeyboardEventInit = {}, target: EventTarget = input) => {
    target.dispatchEvent(new KeyboardEvent('keydown', { key: name, bubbles: true, ...init }));
    await fixture.whenStable();
  };
  const options = () =>
    Array.from(root.querySelectorAll('[role=option]')).map(
      (option) => option.querySelector('.title')!.textContent!,
    );
  return { root, input, navigate, type, key, options };
}

describe('ScreenSearch', () => {
  afterEach(() => localStorage.clear());

  it('combobox ARIA reliée à sa liste', async () => {
    const { input } = await render();
    expect(input.getAttribute('role')).toBe('combobox');
    expect(input.getAttribute('aria-controls')).toBe('screen-search-list');
    expect(input.getAttribute('aria-expanded')).toBe('false');
  });

  it('saisie vide : tout le rail ; une lettre : rien', async () => {
    const { type, options, root } = await render();
    await type('');
    expect(options()).toHaveLength(SCREENS.length);
    await type('c');
    expect(options()).toEqual([]);
    expect(root.querySelector('.empty')?.textContent).toContain('deux lettres');
  });

  it('terme sans accent et mot du métier', async () => {
    const { type, options } = await render();
    await type('parametrage');
    expect(options()[0]).toBe('Informations générales');
    await type('relecteur');
    expect(options()).toEqual(['Confidentialité']);
  });

  it('Entrée sans toucher aux flèches ouvre le premier résultat', async () => {
    const { type, key, navigate, input } = await render();
    await type('echeance');
    await key('Enter');
    expect(navigate).toHaveBeenCalledWith('/editions/3/parametrage/calendrier');
    expect(input.value).toBe('');
  });

  it('flèches en boucle, puis Entrée', async () => {
    const { type, key, navigate } = await render();
    await type('comite');
    await key('ArrowDown');
    await key('Enter');
    expect(navigate).toHaveBeenCalledWith('/editions/3/comites/invitations');
  });

  it('nouvelle saisie : le surlignage revient au premier résultat', async () => {
    const { type, key, navigate } = await render();
    await type('comite');
    await key('ArrowDown');
    await type('journal');
    await key('Enter');
    expect(navigate).toHaveBeenCalledWith('/editions/3/audit');
  });

  it('clic souris (mousedown) sur un résultat', async () => {
    const { type, root, navigate } = await render();
    await type('membres');
    const option = root.querySelector('[role=option]')!;
    const event = new MouseEvent('mousedown', { bubbles: true, cancelable: true });
    option.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
    expect(navigate).toHaveBeenCalledWith('/editions/3/comites/membres');
  });

  it('Ctrl+K met le focus dans le champ depuis la page', async () => {
    const { input, key } = await render();
    await key('k', { ctrlKey: true }, document);
    expect(document.activeElement).toBe(input);
  });

  it('Échap vide la saisie', async () => {
    const { type, key, input, options } = await render();
    await type('journal');
    await key('Escape');
    expect(input.value).toBe('');
    expect(options()).toHaveLength(SCREENS.length);
  });

  it('profil restreint : un écran hors périmètre est introuvable', async () => {
    const { type, options } = await render({
      ...CHAIR_EDITION,
      roles: [{ role: 'OC_MEMBER', oc_function: 'communication' }],
      capabilities: ['edition.read'],
    });
    await type('journal');
    expect(options()).toEqual([]);
    await type('invitations');
    expect(options()).toEqual([]);
  });
});

import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { useTestLanguage } from '@gestconf/shared/testing';

import { provideGestionTesting } from '../../testing/gestion-testing';
import { ContextHelp } from './context-help';

@Component({ template: '' })
class Blank {}

async function render(url: string) {
  TestBed.configureTestingModule({
    imports: [ContextHelp],
    providers: provideGestionTesting(undefined, [{ path: '**', component: Blank }]),
  });
  await useTestLanguage('fr');
  await TestBed.inject(Router).navigateByUrl(url);
  const fixture = TestBed.createComponent(ContextHelp);
  await fixture.whenStable();
  return { fixture, root: fixture.nativeElement as HTMLElement };
}

describe('ContextHelp', () => {
  it('écran avec fiche : bouton « ? », tiroir avec la fiche de l’écran', async () => {
    const { fixture, root } = await render('/editions/3/parametrage/calendrier');
    const button = root.querySelector<HTMLButtonElement>('.help-button')!;
    expect(button.getAttribute('aria-label')).toBe('Aide sur cet écran');
    button.click();
    await fixture.whenStable();
    const drawer = root.querySelector('[role=dialog]')!;
    expect(drawer.querySelector('h2')?.textContent).toContain('Calendrier');
    expect(drawer.querySelector('a')?.getAttribute('href')).toBe('/aide?fiche=settings-calendar');
    // Pas d'ancre dans le tiroir (elle appartient à la page /aide).
    expect(drawer.querySelector('[id^=fiche-]')).toBeNull();
  });

  it('Échap referme le tiroir', async () => {
    const { fixture, root } = await render('/editions/3/audit');
    root.querySelector<HTMLButtonElement>('.help-button')!.click();
    await fixture.whenStable();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    await fixture.whenStable();
    expect(root.querySelector('[role=dialog]')).toBeNull();
  });

  it('clic sur le fond referme le tiroir', async () => {
    const { fixture, root } = await render('/editions/3/audit');
    root.querySelector<HTMLButtonElement>('.help-button')!.click();
    await fixture.whenStable();
    root.querySelector<HTMLElement>('.backdrop')!.click();
    await fixture.whenStable();
    expect(root.querySelector('[role=dialog]')).toBeNull();
  });

  it('écran sans fiche : aucun bouton', async () => {
    const { root } = await render('/acces-refuse');
    expect(root.querySelector('.help-button')).toBeNull();
  });

  it('sur le guide lui-même : aucun bouton', async () => {
    const { root } = await render('/aide');
    expect(root.querySelector('.help-button')).toBeNull();
  });
});

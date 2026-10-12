import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideI18nTesting, useTestLanguage } from '../../testing';
import { ScrollRegion } from './scroll-region';

@Component({
  imports: [ScrollRegion],
  template: `<div class="table-wrap"><table></table></div>
    <div class="autre"></div>`,
})
class Host {}

describe('ScrollRegion (audit axe, L9.6)', () => {
  it('rend chaque .table-wrap atteignable au clavier et nommé', async () => {
    TestBed.configureTestingModule({ imports: [Host], providers: [provideI18nTesting()] });
    await useTestLanguage('fr');
    const fixture = TestBed.createComponent(Host);
    fixture.detectChanges();
    const root = fixture.nativeElement as HTMLElement;
    const wrap = root.querySelector<HTMLElement>('.table-wrap')!;
    expect(wrap.getAttribute('tabindex')).toBe('0');
    expect(wrap.getAttribute('role')).toBe('region');
    expect(wrap.getAttribute('aria-label')).toBe(
      'Tableau : défilement horizontal au clavier (flèches)',
    );
    expect(root.querySelector('.autre')!.hasAttribute('tabindex')).toBe(false);
  });
});

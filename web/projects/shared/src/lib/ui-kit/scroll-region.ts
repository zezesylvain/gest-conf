import { Directive, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { TranslateService } from '@ngx-translate/core';

/**
 * Zone de défilement horizontal des tableaux (classe `table-wrap`) : atteignable au clavier
 * et nommée pour les lecteurs d'écran (WCAG 2.1.1 et 4.1.2 ; constat de l'audit axe de
 * L9.6, règle `scrollable-region-focusable`). S'applique d'elle-même à tout élément de
 * classe `table-wrap` d'un composant qui l'importe.
 */
@Directive({
  // eslint-disable-next-line @angular-eslint/directive-selector -- classe déjà portée par les 48 tableaux
  selector: '.table-wrap',
  host: {
    tabindex: '0',
    role: 'region',
    '[attr.aria-label]': 'label()',
  },
})
export class ScrollRegion {
  protected readonly label = toSignal(
    inject(TranslateService).stream('shared.table.scrollRegion'),
    { initialValue: '' },
  );
}

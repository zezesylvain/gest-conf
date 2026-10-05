import { afterNextRender, ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
import { AuthApi, LanguageSwitcher, SessionStore } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

@Component({
  selector: 'portail-root',
  imports: [RouterOutlet, RouterLink, TranslatePipe, LanguageSwitcher],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  protected readonly session = inject(SessionStore);
  private readonly authApi = inject(AuthApi);

  constructor() {
    // État de session lu dans le navigateur seulement, jamais au pré-rendu (plan L1 §10.4).
    afterNextRender(() => {
      if (this.session.state() === 'unknown') {
        void this.authApi.loadSession().catch(() => this.session.clear());
      }
    });
  }
}

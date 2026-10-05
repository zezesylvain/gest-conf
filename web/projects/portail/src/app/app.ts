import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink, RouterOutlet } from '@angular/router';
import { LanguageSwitcher } from '@gestconf/shared';
import { TranslatePipe } from '@ngx-translate/core';

@Component({
  selector: 'portail-root',
  imports: [RouterOutlet, RouterLink, TranslatePipe, LanguageSwitcher],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {}

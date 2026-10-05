import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Title } from '@angular/platform-browser';
import { provideRouter, Router, TitleStrategy } from '@angular/router';

import { provideI18nTesting, useTestLanguage } from '../../testing';
import { TranslationImporters } from './json-import-loader';
import { LanguageService } from './language.service';
import { TranslatedTitleStrategy } from './translated-title.strategy';

@Component({ template: '' })
class Dummy {}

const pages: TranslationImporters = {
  fr: async () => ({ default: { pages: { home: 'Accueil' } } }),
  en: async () => ({ default: { pages: { home: 'Home' } } }),
};

describe('TranslatedTitleStrategy', () => {
  beforeEach(async () => {
    TestBed.configureTestingModule({
      providers: [
        provideI18nTesting(pages),
        provideRouter([{ path: '', title: 'pages.home', component: Dummy }]),
        { provide: TitleStrategy, useClass: TranslatedTitleStrategy },
      ],
    });
    await useTestLanguage('fr');
    await TestBed.inject(Router).navigateByUrl('/');
  });

  it('traduit la clé de titre de la route', () => {
    expect(TestBed.inject(Title).getTitle()).toBe('Accueil · GEST-CONF');
  });

  it('met à jour le titre au changement de langue', async () => {
    await TestBed.inject(LanguageService).use('en', { remember: false });
    expect(TestBed.inject(Title).getTitle()).toBe('Home · GEST-CONF');
  });
});

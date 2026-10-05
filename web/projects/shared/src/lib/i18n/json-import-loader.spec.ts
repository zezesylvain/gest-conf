import { firstValueFrom } from 'rxjs';

import { JsonImportLoader, TranslationImporters } from './json-import-loader';

const common: TranslationImporters = {
  fr: async () => ({ default: { shared: { hello: 'Bonjour' } } }),
  en: async () => ({ default: { shared: { hello: 'Hello' } } }),
};

const app: TranslationImporters = {
  fr: async () => ({ default: { shared: { extra: 'En plus' }, app: { title: 'Accueil' } } }),
  en: async () => ({ default: { shared: { extra: 'Extra' }, app: { title: 'Home' } } }),
};

describe('JsonImportLoader', () => {
  it('fusionne en profondeur les traductions communes et celles de l’application', async () => {
    const translations = await firstValueFrom(
      new JsonImportLoader([common, app]).getTranslation('en'),
    );
    expect(translations).toEqual({
      shared: { hello: 'Hello', extra: 'Extra' },
      app: { title: 'Home' },
    });
  });

  it('se replie sur le français pour une langue non prise en charge', async () => {
    const translations = await firstValueFrom(new JsonImportLoader([common]).getTranslation('de'));
    expect(translations).toEqual({ shared: { hello: 'Bonjour' } });
  });
});

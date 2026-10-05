import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { provideI18nTesting, useTestLanguage } from '../../testing';
import { ApiStatus } from './api-status';

describe('ApiStatus', () => {
  let fixture: ComponentFixture<ApiStatus>;
  let http: HttpTestingController;

  const element = (): HTMLElement => fixture.nativeElement.querySelector('[role="status"]');

  async function settle(): Promise<void> {
    await vi.waitFor(() => expect(element().dataset['state']).not.toBe('checking'));
    await fixture.whenStable();
  }

  beforeEach(async () => {
    TestBed.configureTestingModule({
      imports: [ApiStatus],
      providers: [provideHttpClient(), provideHttpClientTesting(), provideI18nTesting()],
    });
    await useTestLanguage('fr');
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(ApiStatus);
    await fixture.whenStable();
  });

  afterEach(() => http.verify());

  it('interroge /api/v1/health et affiche « opérationnelle »', async () => {
    expect(element().textContent).toContain('Vérification');
    http
      .expectOne('/api/v1/health')
      .flush({ status: 'ok', database: 'ok', secure: true, release: 'dev' });
    await settle();
    expect(element().dataset['state']).toBe('ok');
    expect(element().textContent).toContain('API opérationnelle');
  });

  it('signale une API dégradée (503, base indisponible)', async () => {
    http
      .expectOne('/api/v1/health')
      .flush(
        { status: 'degraded', database: 'error', secure: true, release: 'dev' },
        { status: 503, statusText: 'Service Unavailable' },
      );
    await settle();
    expect(element().dataset['state']).toBe('degraded');
  });

  it('signale une API injoignable (erreur réseau)', async () => {
    http.expectOne('/api/v1/health').error(new ProgressEvent('error'));
    await settle();
    expect(element().dataset['state']).toBe('unreachable');
    expect(element().textContent).toContain('API injoignable');
  });
});

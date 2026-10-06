import { HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { provideAccountTesting } from '../testing';
import { callIsOpen, SubmissionsService, wordCount } from './submissions.service';
import { testEdition, testSubmission } from './testing';

describe('wordCount', () => {
  it('compte comme le serveur : apostrophes et traits d’union internes, nombres', () => {
    // Même cas que test_word_count_keeps_apostrophes_and_hyphens_inside_words (backend).
    expect(wordCount("L'appel bien-être, aujourd’hui : 3 jours.")).toBe(5);
    expect(wordCount('')).toBe(0);
    expect(wordCount('  — ; ')).toBe(0);
  });
});

describe('callIsOpen', () => {
  const edition = testEdition();

  it('ouvert entre « call_open » et « call_close » (fin exclue)', () => {
    expect(callIsOpen(edition, Date.parse('2026-06-01T00:00:00Z'))).toBe(true);
    expect(callIsOpen(edition, Date.parse('2025-12-31T23:59:59Z'))).toBe(false);
    expect(callIsOpen(edition, Date.parse('2026-12-31T23:59:00Z'))).toBe(false);
  });

  it('fermé si une date manque', () => {
    expect(callIsOpen(testEdition({ key_dates: [] }))).toBe(false);
  });
});

describe('SubmissionsService', () => {
  let service: SubmissionsService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: provideAccountTesting() });
    service = TestBed.inject(SubmissionsService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('écritures : la révision lue part en If-Match (412 si modifiée ailleurs)', async () => {
    const pending = service.update(testSubmission({ revision: 3 }), { title: 'Nouveau' });
    await Promise.resolve();
    const request = http.expectOne((req) => req.url.endsWith('/v1/submissions/7'));
    expect(request.request.method).toBe('PATCH');
    expect(request.request.headers.get('If-Match')).toBe('3');
    expect(request.request.body).toEqual({ title: 'Nouveau' });
    request.flush(testSubmission({ revision: 4, title: 'Nouveau' }));
    expect((await pending).revision).toBe(4);
  });

  it('auteurs et fichier : If-Match aussi', async () => {
    const submission = testSubmission({ revision: 5 });
    void service.setAuthors(submission, []);
    void service.removeFile(submission);
    await Promise.resolve();
    for (const request of [
      http.expectOne((req) => req.url.endsWith('/v1/submissions/7/authors')),
      http.expectOne((req) => req.url.endsWith('/v1/submissions/7/file')),
    ]) {
      expect(request.request.headers.get('If-Match')).toBe('5');
      request.flush(submission);
    }
  });

  it('fichier courant : endpoint authentifié (règle n° 8)', () => {
    expect(service.fileUrl(7)).toBe('/api/v1/submissions/7/file/content');
    expect(service.finalVersionUrl(7)).toBe('/api/v1/submissions/7/final-version/content');
  });

  it('version finale (H18) : multipart, PDF et lettre de réponse, sans If-Match', async () => {
    const file = new File(['%PDF-1.4'], 'final.pdf', { type: 'application/pdf' });
    const pending = service.finalVersion(7, file, 'Merci aux relecteurs.');
    await Promise.resolve();
    const request = http.expectOne((req) => req.url.endsWith('/v1/submissions/7/final-version'));
    expect(request.request.method).toBe('POST');
    expect(request.request.headers.has('If-Match')).toBe(false);
    const body = request.request.body as FormData;
    expect(body.get('file')).toBeInstanceOf(File);
    expect(body.get('response_letter')).toBe('Merci aux relecteurs.');
    request.flush(testSubmission({ status: 'camera_ready_received' }));
    expect((await pending).status).toBe('camera_ready_received');
  });
});

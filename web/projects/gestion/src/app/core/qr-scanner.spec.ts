import { createDecoder, preparedDecoder, ScanDebouncer } from './qr-scanner';

describe('Lecture du QR (plan L7, K6)', () => {
  it('même badge devant la caméra : rendu une fois par fenêtre ; un autre badge, aussitôt', () => {
    const debouncer = new ScanDebouncer(3000);
    expect(debouncer.accept('a', 0)).toBe(true);
    expect(debouncer.accept('a', 1000)).toBe(false);
    expect(debouncer.accept('b', 1100)).toBe(true);
    expect(debouncer.accept('b', 5000)).toBe(true);
  });

  it('BarcodeDetector présent et capable de lire les QR : utilisé, sans charger jsQR', async () => {
    const detect = vi.fn().mockResolvedValue([{ rawValue: 'jeton' }]);
    class Detector {
      static getSupportedFormats = async () => ['qr_code', 'ean_13'];
      constructor(readonly options: { formats: string[] }) {}
      detect = detect;
    }
    const decode = await createDecoder({ BarcodeDetector: Detector as never });
    const video = document.createElement('video');
    expect(await decode(video, document.createElement('canvas'))).toBe('jeton');
    expect(detect).toHaveBeenCalledWith(video);
  });

  it('sans BarcodeDetector : jsQR, rien tant que la vidéo n’a pas d’image', async () => {
    const decode = await createDecoder({});
    const video = document.createElement('video');
    expect(await decode(video, document.createElement('canvas'))).toBeNull();
  });

  it('décodeur préparé à l’ouverture de l’accueil : un seul chargement, réutilisé', async () => {
    const first = preparedDecoder();
    expect(preparedDecoder()).toBe(first);
    expect(typeof (await first)).toBe('function');
  });
});

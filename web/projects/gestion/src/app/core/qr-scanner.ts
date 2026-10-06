/**
 * Lecture du QR d'un badge par la caméra (plan L7, K6 ; bilan de L7.0) : `getUserMedia`,
 * puis décodage **sur l'appareil** (aucun flux envoyé au serveur), par l'API
 * `BarcodeDetector` quand elle existe (Chrome Android), sinon par `jsQR`, chargé à la
 * demande dans le seul écran d'accueil.
 */

/** Décodeur d'une image de la vidéo : texte du QR, ou `null`. */
export type FrameDecoder = (
  video: HTMLVideoElement,
  canvas: HTMLCanvasElement,
) => Promise<string | null>;

interface DetectedBarcode {
  rawValue: string;
}

interface BarcodeDetectorLike {
  detect(source: CanvasImageSource): Promise<DetectedBarcode[]>;
}

interface BarcodeDetectorConstructor {
  new (options: { formats: string[] }): BarcodeDetectorLike;
  getSupportedFormats?: () => Promise<string[]>;
}

/** Côté le plus long de l'image décodée par `jsQR` : assez pour un badge à 20 cm. */
const MAX_SIDE = 720;

export async function createDecoder(
  scope: { BarcodeDetector?: BarcodeDetectorConstructor } = globalThis as never,
): Promise<FrameDecoder> {
  const Detector = scope.BarcodeDetector;
  if (Detector) {
    try {
      const formats = (await Detector.getSupportedFormats?.()) ?? ['qr_code'];
      if (formats.includes('qr_code')) {
        const detector = new Detector({ formats: ['qr_code'] });
        return async (video) => (await detector.detect(video))[0]?.rawValue ?? null;
      }
    } catch {
      // API présente mais inutilisable : repli sur jsQR.
    }
  }
  const { default: jsQR } = await import('jsqr');
  return async (video, canvas) => {
    const { videoWidth: width, videoHeight: height } = video;
    if (!width || !height) {
      return null;
    }
    const scale = Math.min(1, MAX_SIDE / Math.max(width, height));
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    const context = canvas.getContext('2d', { willReadFrequently: true });
    if (!context) {
      return null;
    }
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const image = context.getImageData(0, 0, canvas.width, canvas.height);
    return (
      jsQR(image.data, image.width, image.height, { inversionAttempts: 'attemptBoth' })?.data ??
      null
    );
  };
}

/**
 * Un badge reste devant la caméra plusieurs images de suite : le même texte n'est rendu
 * qu'une fois par fenêtre de `windowMs` (un autre badge passe aussitôt).
 */
export class ScanDebouncer {
  private last: { text: string; at: number } | null = null;

  constructor(private readonly windowMs = 3000) {}

  accept(text: string, now = Date.now()): boolean {
    if (this.last && this.last.text === text && now - this.last.at < this.windowMs) {
      return false;
    }
    this.last = { text, at: now };
    return true;
  }

  reset(): void {
    this.last = null;
  }
}

/** Caméra arrière, vidéo en ligne (iOS), lecture d'environ huit images par seconde. */
export class QrScanner {
  private stream: MediaStream | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private running = false;
  private readonly debouncer = new ScanDebouncer();

  constructor(
    private readonly video: HTMLVideoElement,
    private readonly canvas: HTMLCanvasElement,
    private readonly onCode: (text: string) => void,
    private readonly decoder: () => Promise<FrameDecoder> = () => createDecoder(),
  ) {}

  get active(): boolean {
    return this.running;
  }

  async start(): Promise<void> {
    if (this.running) {
      return;
    }
    const decode = await this.decoder();
    this.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' } },
      audio: false,
    });
    this.video.setAttribute('playsinline', '');
    this.video.muted = true;
    this.video.srcObject = this.stream;
    await this.video.play();
    this.running = true;
    this.debouncer.reset();
    const tick = async () => {
      if (!this.running) {
        return;
      }
      try {
        const text = await decode(this.video, this.canvas);
        if (text && this.debouncer.accept(text)) {
          this.onCode(text);
        }
      } catch {
        // Image illisible : la suivante.
      }
      if (this.running) {
        this.timer = setTimeout(tick, 120);
      }
    };
    void tick();
  }

  stop(): void {
    this.running = false;
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.video.srcObject = null;
  }
}

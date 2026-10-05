import { TestBed } from '@angular/core/testing';
import { GcApiError, Profile } from '@gestconf/shared';
import { provideAuthTesting, useTestLanguage } from '@gestconf/shared/testing';

import { AccountService } from '../account.service';
import { provideAccountTesting } from '../testing';
import { ProfilePage } from './profile-page';

const PROFILE: Profile = {
  title: 'dr',
  first_name: 'Awa',
  last_name: 'Koné',
  institution: 'UFHB',
  department: '',
  country: 'CI',
  orcid: '',
  bio: '',
  website: '',
  scholar_url: '',
  linkedin_url: '',
  photo_url: null,
  is_complete: true,
};

describe('ProfilePage', () => {
  let updateProfile: ReturnType<typeof vi.fn>;
  let uploadPhoto: ReturnType<typeof vi.fn>;

  beforeEach(async () => {
    updateProfile = vi.fn().mockResolvedValue(PROFILE);
    uploadPhoto = vi
      .fn()
      .mockResolvedValue({ ...PROFILE, photo_url: '/api/v1/public/files/x/photo.png' });
    TestBed.configureTestingModule({
      imports: [ProfilePage],
      providers: [
        ...provideAccountTesting(),
        ...provideAuthTesting(),
        {
          provide: AccountService,
          useValue: {
            profile: vi.fn().mockResolvedValue(PROFILE),
            updateProfile,
            uploadPhoto,
            deletePhoto: vi.fn().mockResolvedValue(PROFILE),
          },
        },
      ],
    });
    await useTestLanguage('fr');
  });

  async function render() {
    const fixture = TestBed.createComponent(ProfilePage);
    await fixture.whenStable();
    fixture.detectChanges();
    return fixture;
  }

  it('charge le profil et nomme les pays dans la langue de l’interface', async () => {
    const fixture = await render();
    const root: HTMLElement = fixture.nativeElement;
    const inputs = Array.from(root.querySelectorAll<HTMLInputElement>('input'));
    expect(inputs.map((input) => input.value)).toContain('Koné');
    expect(root.textContent).toContain('Côte d’Ivoire');
  });

  it('erreur du serveur sur l’ORCID : affichée sur le champ', async () => {
    updateProfile.mockRejectedValue(
      new GcApiError(400, 'validation_error', 'Données invalides.', {
        orcid: ['Identifiant ORCID invalide (forme 0000-0000-0000-000X).'],
      }),
    );
    const fixture = await render();
    const root: HTMLElement = fixture.nativeElement;
    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    fixture.detectChanges();
    expect(updateProfile).toHaveBeenCalled();
    expect(root.textContent).toContain('Identifiant ORCID invalide');
  });

  it('enregistrement : message de confirmation', async () => {
    const fixture = await render();
    const root: HTMLElement = fixture.nativeElement;
    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    fixture.detectChanges();
    expect(root.textContent).toContain('Modifications enregistrées.');
  });

  it('photo : envoyée au serveur, aperçu par l’adresse authentifiée', async () => {
    const fixture = await render();
    const root: HTMLElement = fixture.nativeElement;
    expect(root.querySelector('.photo img')).toBeNull();
    const input = root.querySelector<HTMLInputElement>('.photo input[type=file]')!;
    const photo = new File(['x'], 'moi.png', { type: 'image/png' });
    Object.defineProperty(input, 'files', { value: [photo] });
    input.dispatchEvent(new Event('change'));
    await fixture.whenStable();
    fixture.detectChanges();
    expect(uploadPhoto).toHaveBeenCalledWith(photo);
    expect(root.querySelector('.photo img')?.getAttribute('src')).toMatch(
      /^\/api\/v1\/me\/photo\?v=\d+$/,
    );
    expect(root.textContent).toContain('Photo enregistrée.');
  });

  it('lien public non https : refusé avant l’envoi', async () => {
    const fixture = await render();
    const root: HTMLElement = fixture.nativeElement;
    const website = root.querySelector<HTMLInputElement>('.profile-links input')!;
    website.value = 'http://moi.example';
    website.dispatchEvent(new Event('input'));
    root.querySelector('form')!.dispatchEvent(new Event('submit'));
    await fixture.whenStable();
    expect(updateProfile).not.toHaveBeenCalled();
  });
});

import { inject, Injectable } from '@angular/core';
import {
  Api,
  PublicProgram,
  publicProgram,
  PublicProgramDay,
  publicProgramDay,
  publicProgramSession,
  PublicSession,
} from '@gestconf/shared';

/**
 * Programme publié (plan L5, I7), par l'API publique : jamais le brouillon. Lu au pré-rendu
 * et transféré au navigateur avec la page (une réponse par page, bilan de L5.0).
 */
@Injectable({ providedIn: 'root' })
export class ProgramData {
  private readonly api = inject(Api);

  summary(): Promise<PublicProgram> {
    return this.api.invoke(publicProgram);
  }

  day(day: string): Promise<PublicProgramDay> {
    return this.api.invoke(publicProgramDay, { day });
  }

  session(id: number): Promise<PublicSession> {
    return this.api.invoke(publicProgramSession, { session_id: id });
  }
}

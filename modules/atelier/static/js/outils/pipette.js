import { prelever } from '../echantillon.js';
import { sourceOption } from './options.js';

let source = 'visibles';
export default {
  id: 'pipette', libelle: 'Pipette', raccourci: 'i', curseur: 'crosshair',
  panneauOptions() {
    const panneau = document.createElement('div'); sourceOption(panneau, source, valeur => { source = valeur; }); return panneau;
  },
  pointeurBas(ctx, e) { if (e.button === 0 && !ctx.occupe) prelever(ctx, e, source === 'visibles'); }
};

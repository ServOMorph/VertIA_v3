import { creerElement } from '../elements/registre.js';
import { ajouterElement, trouverElement, couleurCourante, cadreSelection, proprietesElement, editerTexte, supprimerSelection } from './elements.js';

export default {
  id: 'texte', libelle: 'Texte', raccourci: 't', curseur: 'text',
  panneauOptions(ctx) {
    const p = document.createElement('div'), aide = document.createElement('p');
    aide.textContent = 'Cliquer pour créer un texte. Double-cliquer sur un texte pour le modifier. Valider la saisie en quittant le champ.';
    p.append(aide); proprietesElement(ctx, p); return p;
  },
  dessinerSurimpression: cadreSelection,
  pointeurBas(ctx, e) {
    if (e.button !== 0 || ctx.occupe) return;
    const point = ctx.vue.coordonnees(e), existant = trouverElement(ctx, point, 'texte');
    if (existant) { ctx.document.actifId = existant.id; ctx.notifier(); ctx.actualiserOptions?.(); return; }
    const c = ajouterElement(ctx, creerElement('texte', { x: point.x, y: point.y, couleur: couleurCourante(ctx) }), 'Texte');
    c.opacite = ctx.couleur[3]; editerTexte(ctx);
  },
  doubleClic(ctx, e) {
    const c = trouverElement(ctx, ctx.vue.coordonnees(e), 'texte');
    if (c) { ctx.document.actifId = c.id; ctx.notifier(); editerTexte(ctx); }
  },
  touche(ctx, e) { if (e.key === 'Delete' || e.key === 'Backspace') return supprimerSelection(ctx); }
};

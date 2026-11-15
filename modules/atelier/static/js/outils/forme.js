import { creerElement, dessinerElement } from '../elements/registre.js';
import { depuisGlissement } from '../elements/geometrie.js';
import { ajouterElement, couleurCourante, cadreSelection, proprietesElement, champ, supprimerSelection } from './elements.js';

let type = 'rectangle', epaisseur = 2, remplir = false, geste = null;
export default {
  id: 'forme', libelle: 'Formes', raccourci: 'u', curseur: 'crosshair',
  desactiver(ctx) { geste = null; ctx.vue.invalider(); },
  panneauOptions(ctx) {
    const p = document.createElement('div');
    champ(p, 'Nouvelle forme', 'select', type, v => { type = v; }, [['rectangle', 'Rectangle'], ['ellipse', 'Ellipse'], ['ligne', 'Ligne']]);
    const largeur = champ(p, 'Nouveau trait (px)', 'number', epaisseur, v => { epaisseur = v; }); largeur.max = 300;
    champ(p, 'Remplir la nouvelle forme', 'checkbox', remplir, v => { remplir = v; });
    proprietesElement(ctx, p); return p;
  },
  dessinerSurimpression(ctx, rendu) {
    cadreSelection(ctx, rendu);
    if (geste) { rendu.save(); rendu.globalAlpha = geste.alpha; dessinerElement(rendu, geste.element); rendu.restore(); }
  },
  pointeurBas(ctx, e) {
    if (e.button !== 0 || ctx.occupe) return;
    const debut = ctx.vue.coordonnees(e), couleur = couleurCourante(ctx);
    geste = { debut, alpha: ctx.couleur[3], element: creerElement(type, { ...depuisGlissement(type, debut, debut),
      couleur, epaisseur, remplissage: remplir && type !== 'ligne' ? couleur : null }) };
  },
  pointeurDeplace(ctx, e) {
    if (!geste) return;
    geste.element = { ...geste.element, ...depuisGlissement(geste.element.type, geste.debut, ctx.vue.coordonnees(e), e.shiftKey) };
    ctx.vue.invalider();
  },
  pointeurHaut(ctx, e) {
    if (!geste) return;
    if (e.type === 'pointerup') {
      this.pointeurDeplace(ctx, e);
      const c = ajouterElement(ctx, geste.element, 'Forme'); c.opacite = geste.alpha;
    }
    geste = null; ctx.vue.invalider();
  },
  touche(ctx, e) { if (e.key === 'Delete' || e.key === 'Backspace') return supprimerSelection(ctx); }
};

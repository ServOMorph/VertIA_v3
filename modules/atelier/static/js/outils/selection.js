import deplacer from './deplacer.js';
import { boiteElement, copierElement } from '../elements/registre.js';
import { toucherPoignee, redimensionner } from '../elements/geometrie.js';
import { trouverElement, cadreSelection, proprietesElement, supprimerSelection, editerTexte } from './elements.js';

let geste = null, raster = false;
function terminer(ctx, annuler) {
  if (!geste) return;
  const g = geste; geste = null;
  const apres = { x: g.calque.x, y: g.calque.y, donnees: copierElement(g.calque.donnees) };
  const appliquer = valeurs => { Object.assign(g.calque, valeurs); ctx.notifier(); };
  if (annuler) appliquer(g.avant);
  else if (JSON.stringify(apres) !== JSON.stringify(g.avant)) ctx.historique.enregistrer({ libelle: 'Transformer l’élément',
    annuler: () => appliquer(g.avant), retablir: () => appliquer(apres) });
  ctx.actualiserOptions?.();
}
export default {
  id: 'selection', libelle: 'Déplacer / Sélection', raccourci: 'v', curseur: 'default',
  desactiver(ctx) { terminer(ctx, true); deplacer.desactiver(ctx); raster = false; },
  panneauOptions(ctx) {
    const p = document.createElement('div'), aide = document.createElement('p');
    aide.textContent = 'Cliquer : sélectionner. Glisser : déplacer. Poignées : redimensionner (Maj : proportions). Suppr : supprimer. Bouton central : défiler.';
    p.append(aide); proprietesElement(ctx, p); return p;
  },
  dessinerSurimpression: cadreSelection,
  pointeurBas(ctx, e) {
    if (ctx.occupe) return;
    const point = ctx.vue.coordonnees(e), actif = ctx.calqueActif;
    let cible = actif?.type === 'element' && actif.visible ? actif : null;
    const b = cible && boiteElement(cible.donnees);
    const poignee = b ? toucherPoignee(b, { x: point.x - cible.x, y: point.y - cible.y }, 6 / ctx.vue.zoom) : -1;
    if (poignee < 0) cible = trouverElement(ctx, point);
    if (e.button === 1 || (!cible && actif?.type === 'raster')) {
      raster = true; deplacer.pointeurBas(ctx, e); return;
    }
    if (e.button !== 0) return;
    ctx.document.actifId = cible?.id ?? null; ctx.notifier(); ctx.actualiserOptions?.();
    if (!cible) return;
    geste = { calque: cible, debut: point, poignee,
      avant: { x: cible.x, y: cible.y, donnees: copierElement(cible.donnees) } };
  },
  pointeurDeplace(ctx, e) {
    if (raster) { deplacer.pointeurDeplace(ctx, e); return; }
    if (!geste) return;
    const g = geste, point = ctx.vue.coordonnees(e);
    if (g.poignee >= 0) g.calque.donnees = redimensionner(g.avant.donnees, g.poignee,
      { x: point.x - g.avant.x, y: point.y - g.avant.y }, e.shiftKey);
    else { g.calque.x = g.avant.x + point.x - g.debut.x; g.calque.y = g.avant.y + point.y - g.debut.y; }
    ctx.notifier();
  },
  pointeurHaut(ctx, e) {
    if (raster) { deplacer.pointeurHaut(ctx, e); raster = false; return; }
    if (e.type === 'pointerup') this.pointeurDeplace(ctx, e);
    terminer(ctx, e.type !== 'pointerup');
  },
  doubleClic(ctx, e) {
    const c = trouverElement(ctx, ctx.vue.coordonnees(e), 'texte');
    if (c) { ctx.document.actifId = c.id; ctx.notifier(); editerTexte(ctx); }
  },
  touche(ctx, e) { if (e.key === 'Delete' || e.key === 'Backspace') return supprimerSelection(ctx); }
};

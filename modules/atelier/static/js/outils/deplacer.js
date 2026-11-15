let geste = null;
function terminer(ctx, annuler = false) {
  if (!geste) return;
  const g = geste; geste = null;
  if (g.defiler) return;
  const apres = { x: g.calque.x, y: g.calque.y };
  const appliquer = position => { Object.assign(g.calque, position); ctx.notifier(); };
  if (annuler) appliquer(g.avant);
  else if (apres.x !== g.avant.x || apres.y !== g.avant.y) {
    ctx.historique.enregistrer({ libelle: 'Déplacer le calque',
      annuler: () => appliquer(g.avant), retablir: () => appliquer(apres) });
  }
}
export default {
  id: 'deplacer', libelle: 'Déplacer', raccourci: 'v', curseur: 'move',
  desactiver(ctx) { terminer(ctx, true); },
  panneauOptions() {
    const p = document.createElement('p');
    p.textContent = 'Glisser : déplacer le calque actif. Maj ou bouton central : défiler.';
    return p;
  },
  pointeurBas(ctx, e) {
    const defiler = e.shiftKey || e.button === 1;
    if (!defiler && !ctx.calqueActif) return;
    geste = { defiler, debut: ctx.vue.coordonnees(e), clientX: e.clientX, clientY: e.clientY,
      scrollX: ctx.vue.zone.scrollLeft, scrollY: ctx.vue.zone.scrollTop,
      calque: ctx.calqueActif, avant: ctx.calqueActif ? { x: ctx.calqueActif.x, y: ctx.calqueActif.y } : null };
  },
  pointeurDeplace(ctx, e) {
    if (!geste) return;
    if (geste.defiler) {
      ctx.vue.zone.scrollLeft = geste.scrollX - e.clientX + geste.clientX;
      ctx.vue.zone.scrollTop = geste.scrollY - e.clientY + geste.clientY;
    } else {
      const p = ctx.vue.coordonnees(e);
      geste.calque.x = Math.round(geste.avant.x + p.x - geste.debut.x);
      geste.calque.y = Math.round(geste.avant.y + p.y - geste.debut.y);
      ctx.notifier();
    }
  },
  pointeurHaut(ctx, e) { terminer(ctx, e.type !== 'pointerup'); }
};

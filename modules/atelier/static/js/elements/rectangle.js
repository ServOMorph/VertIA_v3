export function creer(params = {}) {
  return { type: 'rectangle', x: 0, y: 0, largeur: 160, hauteur: 100,
    couleur: '#000000', epaisseur: 2, remplissage: null, ...params };
}
export function boite(e) { return { x: e.x, y: e.y, largeur: e.largeur, hauteur: e.hauteur }; }
export function dessiner(ctx, e) {
  ctx.beginPath(); ctx.rect(e.x, e.y, e.largeur, e.hauteur);
  if (e.remplissage) { ctx.fillStyle = e.remplissage; ctx.fill(); }
  ctx.strokeStyle = e.couleur; ctx.lineWidth = e.epaisseur; ctx.stroke();
}

export function creer(params = {}) {
  return { type: 'ligne', x: 0, y: 0, x2: 160, y2: 100, couleur: '#000000', epaisseur: 2, ...params };
}
export function boite(e) {
  return { x: Math.min(e.x, e.x2), y: Math.min(e.y, e.y2), largeur: Math.abs(e.x2 - e.x), hauteur: Math.abs(e.y2 - e.y) };
}
export function dessiner(ctx, e) {
  ctx.beginPath(); ctx.moveTo(e.x, e.y); ctx.lineTo(e.x2, e.y2);
  ctx.strokeStyle = e.couleur; ctx.lineWidth = e.epaisseur; ctx.stroke();
}

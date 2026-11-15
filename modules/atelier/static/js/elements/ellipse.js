import { creer as rectangle, boite } from './rectangle.js';
export { boite };
export function creer(params = {}) { return rectangle({ ...params, type: 'ellipse' }); }
export function dessiner(ctx, e) {
  ctx.beginPath(); ctx.ellipse(e.x + e.largeur / 2, e.y + e.hauteur / 2, e.largeur / 2, e.hauteur / 2, 0, 0, Math.PI * 2);
  if (e.remplissage) { ctx.fillStyle = e.remplissage; ctx.fill(); }
  ctx.strokeStyle = e.couleur; ctx.lineWidth = e.epaisseur; ctx.stroke();
}

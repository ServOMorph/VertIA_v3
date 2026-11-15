import { boiteElement } from './registre.js';

export function poignees(b) {
  return [[b.x, b.y], [b.x + b.largeur, b.y], [b.x + b.largeur, b.y + b.hauteur], [b.x, b.y + b.hauteur]]
    .map(([x, y]) => ({ x, y }));
}
export function toucherPoignee(b, p, tolerance = 6) {
  return poignees(b).findIndex(q => Math.abs(p.x - q.x) <= tolerance && Math.abs(p.y - q.y) <= tolerance);
}
export function contient(e, p, tolerance = 0) {
  const b = boiteElement(e); if (!b) return false;
  if (e.type === 'ligne') {
    const dx = e.x2 - e.x, dy = e.y2 - e.y, longueur = dx * dx + dy * dy;
    const t = longueur ? Math.max(0, Math.min(1, ((p.x - e.x) * dx + (p.y - e.y) * dy) / longueur)) : 0;
    return Math.hypot(p.x - e.x - t * dx, p.y - e.y - t * dy) <= tolerance + e.epaisseur / 2;
  }
  return p.x >= b.x - tolerance && p.y >= b.y - tolerance
    && p.x <= b.x + b.largeur + tolerance && p.y <= b.y + b.hauteur + tolerance;
}
export function redimensionner(e, index, p, maj = false) {
  const b = boiteElement(e), oppose = poignees(b)[(index + 2) % 4];
  let dx = p.x - oppose.x, dy = p.y - oppose.y;
  if (maj && b.largeur && b.hauteur) {
    const ratio = b.largeur / b.hauteur;
    if (Math.abs(dx) > Math.abs(dy) * ratio) dy = (Math.sign(dy) || (index < 2 ? -1 : 1)) * Math.abs(dx) / ratio;
    else dx = (Math.sign(dx) || ([0, 3].includes(index) ? -1 : 1)) * Math.abs(dy) * ratio;
  }
  if (e.type === 'ligne') {
    if (maj && !b.largeur) dx = 0;
    if (maj && !b.hauteur) dy = 0;
    if (!b.largeur || !b.hauteur) {
      const coin = poignees(b)[index];
      const premier = Math.hypot(e.x - coin.x, e.y - coin.y) <= Math.hypot(e.x2 - coin.x, e.y2 - coin.y);
      return premier ? { ...e, x: oppose.x + dx, y: oppose.y + dy } : { ...e, x2: oppose.x + dx, y2: oppose.y + dy };
    }
    const gauche = [0, 3].includes(index), haut = index < 2;
    const a = { x: gauche ? oppose.x + dx : oppose.x, y: haut ? oppose.y + dy : oppose.y };
    const z = { x: gauche ? oppose.x : oppose.x + dx, y: haut ? oppose.y : oppose.y + dy };
    const transformer = (x, y) => ({ x: a.x + (x - b.x) / b.largeur * (z.x - a.x), y: a.y + (y - b.y) / b.hauteur * (z.y - a.y) });
    const debut = transformer(e.x, e.y), fin = transformer(e.x2, e.y2);
    return { ...e, ...debut, x2: fin.x, y2: fin.y };
  }
  const largeur = Math.max(1, Math.abs(dx)), hauteur = Math.max(1, Math.abs(dy));
  const x = dx < 0 ? oppose.x - largeur : oppose.x, y = dy < 0 ? oppose.y - hauteur : oppose.y;
  return { ...e, x, y, largeur, hauteur };
}
export function depuisGlissement(type, debut, fin, maj = false) {
  let dx = fin.x - debut.x, dy = fin.y - debut.y;
  if (maj) {
    if (type === 'ligne') {
      const angle = Math.round(Math.atan2(dy, dx) / (Math.PI / 4)) * Math.PI / 4, longueur = Math.hypot(dx, dy);
      dx = Math.cos(angle) * longueur; dy = Math.sin(angle) * longueur;
    } else { const taille = Math.max(Math.abs(dx), Math.abs(dy)); dx = (Math.sign(dx) || 1) * taille; dy = (Math.sign(dy) || 1) * taille; }
  }
  return type === 'ligne' ? { x: debut.x, y: debut.y, x2: debut.x + dx, y2: debut.y + dy }
    : { x: Math.min(debut.x, debut.x + dx), y: Math.min(debut.y, debut.y + dy), largeur: Math.max(1, Math.abs(dx)), hauteur: Math.max(1, Math.abs(dy)) };
}

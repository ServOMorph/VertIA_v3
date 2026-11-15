export const POLICES = ['Arial', 'Verdana', 'Georgia', 'Times New Roman', 'Courier New', 'sans-serif', 'serif', 'monospace'];
export function creer(params = {}) {
  return { type: 'texte', x: 0, y: 0, largeur: 300, hauteur: 48, contenu: 'Texte',
    police: 'Arial', taille: 40, couleur: '#000000', gras: false, italique: false, alignement: 'left', ...params };
}
export function boite(e) { return { x: e.x, y: e.y, largeur: e.largeur, hauteur: e.hauteur }; }
export function dessiner(ctx, e) {
  const lignes = e.contenu.split('\n'), interligne = e.taille * 1.2;
  ctx.save(); ctx.translate(e.x, e.y); ctx.scale(1, e.hauteur / (lignes.length * interligne));
  const police = ['sans-serif', 'serif', 'monospace'].includes(e.police) ? e.police : `"${e.police}"`;
  ctx.font = `${e.italique ? 'italic ' : ''}${e.gras ? 'bold ' : ''}${e.taille}px ${police}`;
  ctx.textBaseline = 'top'; ctx.textAlign = e.alignement; ctx.fillStyle = e.couleur;
  const x = e.alignement === 'center' ? e.largeur / 2 : e.alignement === 'right' ? e.largeur : 0;
  lignes.forEach((ligne, i) => ctx.fillText(ligne, x, i * interligne, e.largeur));
  ctx.restore();
}

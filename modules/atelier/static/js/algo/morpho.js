export function dilater(masque, largeur, hauteur, rayon = 1) {
  rayon = Math.max(0, Math.min(3, Math.round(rayon)));
  if (!rayon) return masque.slice();
  const horizontal = new Uint8Array(masque.length), resultat = new Uint8Array(masque.length);
  for (let y = 0; y < hauteur; y++) {
    const ligne = y * largeur;
    for (let x = 0; x < largeur; x++) {
      for (let dx = Math.max(0, x - rayon); dx <= Math.min(largeur - 1, x + rayon); dx++) {
        if (masque[ligne + dx]) { horizontal[ligne + x] = 1; break; }
      }
    }
  }
  for (let y = 0; y < hauteur; y++) {
    for (let x = 0; x < largeur; x++) {
      for (let dy = Math.max(0, y - rayon); dy <= Math.min(hauteur - 1, y + rayon); dy++) {
        if (horizontal[dy * largeur + x]) { resultat[y * largeur + x] = 1; break; }
      }
    }
  }
  return resultat;
}

import { luminance } from './seuil.js';
import { dilater } from './morpho.js';

// Un départ sur le trait ou sur un pixel transparent donne une zone vide.
// L'extension sous le trait ne traverse jamais les pixels libres de la zone voisine.
export function remplir(rgba, largeur, hauteur, trait, x, y, { tolerance = 32, rayon = 1 } = {}) {
  const masque = new Uint8Array(largeur * hauteur), vide = { masque, boite: null };
  x = Math.floor(x); y = Math.floor(y);
  if (x < 0 || y < 0 || x >= largeur || y >= hauteur) return vide;
  const depart = y * largeur + x, s = depart * 4;
  if (trait[depart] || !rgba[s + 3]) return vide;
  tolerance = Math.max(0, Math.min(255, tolerance));
  const reference = luminance(rgba[s], rgba[s + 1], rgba[s + 2]);
  const libre = new Uint8Array(masque.length);
  for (let p = 0, i = 0; p < libre.length; p++, i += 4) {
    libre[p] = !trait[p] && rgba[i + 3] &&
      Math.abs(luminance(rgba[i], rgba[i + 1], rgba[i + 2]) - reference) <= tolerance ? 1 : 0;
  }
  let pile = new Int32Array(Math.min(1024, masque.length)), taille = 0;
  const empiler = p => {
    if (libre[p] !== 1) return;
    libre[p] = 2;
    if (taille === pile.length) {
      const nouvelle = new Int32Array(Math.min(masque.length, pile.length * 2));
      nouvelle.set(pile); pile = nouvelle;
    }
    pile[taille++] = p;
  };
  let gauche = largeur, droite = -1, haut = hauteur, bas = -1;
  empiler(depart);
  while (taille) {
    const p = pile[--taille];
    if (!libre[p]) continue;
    const ligne = Math.floor(p / largeur), origine = ligne * largeur;
    let a = p - origine, b = a;
    while (a > 0 && libre[origine + a - 1]) a--;
    while (b + 1 < largeur && libre[origine + b + 1]) b++;
    for (let xx = a; xx <= b; xx++) { libre[origine + xx] = 0; masque[origine + xx] = 1; }
    gauche = Math.min(gauche, a); droite = Math.max(droite, b);
    haut = Math.min(haut, ligne); bas = Math.max(bas, ligne);
    for (const voisin of [ligne - 1, ligne + 1]) {
      if (voisin < 0 || voisin >= hauteur) continue;
      let dansZone = false;
      for (let xx = a; xx <= b; xx++) {
        const q = voisin * largeur + xx;
        if (!libre[q]) { dansZone = false; continue; }
        if (!dansZone) empiler(q);
        dansZone = true;
      }
    }
  }
  if (rayon > 0) {
    const extension = dilater(masque, largeur, hauteur, rayon);
    for (let p = 0; p < masque.length; p++) {
      if (extension[p] && trait[p]) {
        masque[p] = 1;
        const xx = p % largeur, yy = Math.floor(p / largeur);
        gauche = Math.min(gauche, xx); droite = Math.max(droite, xx);
        haut = Math.min(haut, yy); bas = Math.max(bas, yy);
      }
    }
  }
  return { masque, boite: { x: gauche, y: haut, largeur: droite - gauche + 1, hauteur: bas - haut + 1 } };
}

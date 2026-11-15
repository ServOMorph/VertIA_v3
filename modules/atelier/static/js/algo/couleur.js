export function versHex(couleur) {
  return '#' + couleur.slice(0, 3).map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
}
export function depuisHex(hex) { return [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16)); }

// Composition source-over avec mélange multiply, y compris les deux alphas (Canvas 2D).
export function multiplierPixel(fond, couleur) {
  const ab = fond[3] / 255, as = couleur[3], alpha = as + ab * (1 - as);
  const resultat = new Uint8ClampedArray(4);
  for (let c = 0; c < 3; c++) {
    resultat[c] = alpha ? (as * (1 - ab) * couleur[c] + as * ab * fond[c] * couleur[c] / 255
      + (1 - as) * ab * fond[c]) / alpha : 0;
  }
  resultat[3] = alpha * 255;
  return resultat;
}

export function peindre(rgba, largeur, masque, boite, couleur, multiplier = false) {
  for (let y = boite.y; y < boite.y + boite.hauteur; y++) {
    for (let x = boite.x; x < boite.x + boite.largeur; x++) {
      const p = y * largeur + x, i = p * 4;
      if (!masque[p]) continue;
      // Sur le calque dédié, multiply conserve aussi les remplissages précédents.
      if (multiplier) rgba.set(multiplierPixel(rgba.subarray(i, i + 4), couleur), i);
      else { rgba[i] = couleur[0]; rgba[i + 1] = couleur[1]; rgba[i + 2] = couleur[2]; rgba[i + 3] = couleur[3] * 255; }
    }
  }
  return rgba;
}

export function luminance(r, g, b) { return Math.round(0.299 * r + 0.587 * g + 0.114 * b); }

export function histogramme(rgba) {
  const bins = new Uint32Array(256);
  for (let i = 0; i < rgba.length; i += 4) {
    if (rgba[i + 3]) bins[luminance(rgba[i], rgba[i + 1], rgba[i + 2])]++;
  }
  return bins;
}

export function otsu(bins) {
  let total = 0, somme = 0;
  for (let i = 0; i < 256; i++) { total += bins[i]; somme += i * bins[i]; }
  let poids = 0, cumul = 0, meilleur = -1, debut = 0, fin = 0;
  for (let i = 0; i < 255; i++) {
    poids += bins[i]; cumul += i * bins[i];
    if (!poids || poids === total) continue;
    const delta = cumul / poids - (somme - cumul) / (total - poids);
    const variance = poids * (total - poids) * delta * delta;
    if (variance > meilleur) { meilleur = variance; debut = i; fin = i; }
    else if (variance === meilleur) fin = i;
  }
  // Le masque utilise < seuil : placer la coupure au milieu du plateau optimal.
  return meilleur < 0 ? 128 : Math.floor((debut + fin) / 2) + 1;
}

export function masqueTrait(rgba, largeur, hauteur, seuil = otsu(histogramme(rgba))) {
  const masque = new Uint8Array(largeur * hauteur);
  for (let p = 0, i = 0; p < masque.length; p++, i += 4) {
    masque[p] = rgba[i + 3] && luminance(rgba[i], rgba[i + 1], rgba[i + 2]) < seuil ? 1 : 0;
  }
  return masque;
}

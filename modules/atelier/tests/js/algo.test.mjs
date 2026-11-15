import test from 'node:test';
import assert from 'node:assert/strict';
import { histogramme, otsu, masqueTrait, luminance } from '../../static/js/algo/seuil.js';
import { dilater } from '../../static/js/algo/morpho.js';
import { remplir } from '../../static/js/algo/remplissage.js';
import { peindre, multiplierPixel } from '../../static/js/algo/couleur.js';
import { extraireCouleurs } from '../../static/js/algo/kmeans.js';

function image(w, h, couleur = [255, 255, 255, 255]) {
  const rgba = new Uint8ClampedArray(w * h * 4);
  for (let i = 0; i < w * h; i++) rgba.set(couleur, i * 4);
  return rgba;
}
function carre(trou = false) {
  const rgba = image(11, 11);
  for (let y = 2; y <= 8; y++) for (let x = 2; x <= 8; x++) {
    if ((x === 2 || x === 8 || y === 2 || y === 8) && !(trou && y === 2 && x === 5)) rgba.set([0, 0, 0, 255], (y * 11 + x) * 4);
  }
  return rgba;
}
test('Zone fermée, départ sur trait vide et extension sans liseré', () => {
  const rgba = carre(), trait = masqueTrait(rgba, 11, 11);
  const { masque, boite } = remplir(rgba, 11, 11, dilater(trait, 11, 11), 5, 5);
  assert.equal(masque[0], 0); assert.equal(masque[5 * 11 + 5], 1);
  assert.equal(masque[3 * 11 + 5], 1);
  assert.deepEqual(boite, { x: 3, y: 3, largeur: 5, hauteur: 5 });
  assert.equal(remplir(rgba, 11, 11, trait, 2, 2).boite, null);
});
test('Un trou de 1 px fuit sans dilatation et reste fermé avec rayon 1', () => {
  const rgba = carre(true), trait = masqueTrait(rgba, 11, 11);
  assert.equal(remplir(rgba, 11, 11, trait, 5, 5, { rayon: 0 }).masque[0], 1);
  assert.equal(remplir(rgba, 11, 11, dilater(trait, 11, 11), 5, 5).masque[0], 0);
});
test('Composition multiply utilisée par le pot : noir, gris, blanc et alpha', () => {
  const couleur = [220, 80, 40, 1], rgba = image(3, 1);
  rgba.set([0, 0, 0, 255], 0); rgba.set([100, 100, 100, 255], 4);
  peindre(rgba, 3, new Uint8Array([1, 1, 1]), { x: 0, y: 0, largeur: 3, hauteur: 1 }, couleur, true);
  assert.ok(luminance(...rgba.slice(0, 3)) <= 1);
  assert.deepEqual([...rgba.slice(8)], [220, 80, 40, 255]);
  assert.ok(luminance(...rgba.slice(4, 7)) < 100);
  assert.deepEqual([...multiplierPixel([0, 0, 0, 0], [220, 80, 40, 0.5])], [220, 80, 40, 128]);
  const scan = carre(), zone = remplir(scan, 11, 11, dilater(masqueTrait(scan, 11, 11), 11, 11), 5, 5);
  const calque = image(11, 11, [0, 0, 0, 0]);
  peindre(calque, 11, zone.masque, zone.boite, couleur);
  for (let p = 0; p < 121; p++) {
    const i = p * 4, source = [...calque.slice(i, i + 3), calque[i + 3] / 255];
    const compose = multiplierPixel(scan.slice(i, i + 4), source);
    if (scan[i] === 0) assert.ok(luminance(...compose.slice(0, 3)) <= 1);
    if (p === 60) assert.deepEqual([...compose], [220, 80, 40, 255]);
  }
});
test('Otsu bimodal et transparence', () => {
  const rgba = image(10, 1, [40, 40, 40, 255]);
  for (let p = 5; p < 10; p++) rgba.set([210, 210, 210, 255], p * 4);
  const seuil = otsu(histogramme(rgba)); assert.ok(seuil > 40 && seuil < 210);
  rgba.set([0, 0, 0, 0], 0); assert.equal(masqueTrait(rgba, 10, 1)[0], 0);
});
test('Tolérance, bords et dilatation sans enroulement entre lignes', () => {
  const rgba = image(3, 1); rgba.set([200, 200, 200, 255], 4);
  assert.deepEqual([...remplir(rgba, 3, 1, new Uint8Array(3), 0, 0, { tolerance: 32, rayon: 0 }).masque], [1, 0, 0]);
  assert.equal(remplir(rgba, 3, 1, new Uint8Array(3), -1, 0).boite, null);
  assert.deepEqual([...dilater(new Uint8Array([0, 0, 1, 0, 0, 0]), 3, 2)], [0, 1, 1, 0, 1, 1]);
});
test('K-means retrouve trois couleurs et reste déterministe', () => {
  const rgba = image(90, 1), couleurs = [[255, 0, 0], [0, 255, 0], [0, 0, 255]];
  for (let p = 0; p < 90; p++) rgba.set([...couleurs[Math.floor(p / 30)], 255], p * 4);
  const resultat = extraireCouleurs(rgba, 3);
  assert.deepEqual(resultat, extraireCouleurs(rgba, 3)); assert.equal(resultat.length, 3);
  for (const rgb of couleurs) assert.ok(resultat.some(c => [c.r, c.g, c.b].every((v, i) => Math.abs(v - rgb[i]) <= 2)));
  assert.ok(Math.abs(resultat.reduce((s, c) => s + c.part, 0) - 1) < 1e-9);
  assert.deepEqual(extraireCouleurs(image(2, 1)), []);
  assert.equal(extraireCouleurs(image(2, 1), 2, { ignorerPapierTrait: false }).length, 1);
  assert.deepEqual(extraireCouleurs(image(2, 1, [255, 0, 0, 0])), []);
});
test('Performance indicative : remplissage 3000 × 3000 inférieur à 2 s', t => {
  const rgba = image(3000, 3000), trait = new Uint8Array(9000000), debut = performance.now();
  const resultat = remplir(rgba, 3000, 3000, trait, 1500, 1500);
  const duree = performance.now() - debut; t.diagnostic(`Durée remplissage : ${duree.toFixed(1)} ms`);
  assert.equal(resultat.masque.reduce((s, v) => s + v, 0), 9000000);
  assert.ok(duree < 2000, `Durée ${duree.toFixed(1)} ms > 2000 ms`);
});

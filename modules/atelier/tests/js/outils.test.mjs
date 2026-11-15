import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { Worker as NodeWorker } from 'node:worker_threads';
import { DocumentAtelier, creerRaster } from '../../static/js/document.js';
import { Historique } from '../../static/js/historique.js';
import { calculer } from '../../static/js/calcul.js';
import pot, { appliquerPot } from '../../static/js/outils/pot.js';
import { prelever } from '../../static/js/echantillon.js';
import { serialiser, deserialiser } from '../../static/js/projet.js';
import { installerPalette, nettoyerCouleurs } from '../../static/js/palette.js';
import { multiplierPixel } from '../../static/js/algo/couleur.js';

const workers = [];
globalThis.Worker = class {
  constructor(url) {
    this.worker = new NodeWorker(new URL('./worker-adapter.js', import.meta.url), { workerData: { url: url.href } });
    this.worker.on('message', data => this.onmessage?.({ data }));
    this.worker.on('error', erreur => this.onerror?.(erreur)); workers.push(this.worker);
  }
  postMessage(...args) { this.worker.postMessage(...args); }
  terminate() { this.worker.terminate(); }
};
after(async () => { await Promise.all(workers.map(w => w.terminate())); });

function element(tag) {
  const e = { tag, children: [], style: {}, value: '', append(...enfants) { this.children.push(...enfants); },
    replaceChildren() { this.children = []; }, setAttribute(nom, valeur) { this[nom] = valeur; },
    get options() { return this.children; } };
  if (tag !== 'canvas') return e;
  let pixels;
  const donnees = () => {
    if (!pixels || pixels.length !== e.width * e.height * 4) pixels = new Uint8ClampedArray(e.width * e.height * 4);
    return pixels;
  };
  let tx = 0, ty = 0; const etats = [];
  const ctx = {
    globalAlpha: 1, globalCompositeOperation: 'source-over',
    save() { etats.push([tx, ty, this.globalAlpha, this.globalCompositeOperation]); },
    restore() { [tx, ty, this.globalAlpha, this.globalCompositeOperation] = etats.pop(); },
    translate(x, y) { tx += x; ty += y; },
    drawImage(canvas) {
      const source = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height), cible = donnees();
      for (let y = 0; y < canvas.height; y++) for (let x = 0; x < canvas.width; x++) {
        const xx = Math.floor(x + tx), yy = Math.floor(y + ty);
        if (xx < 0 || yy < 0 || xx >= e.width || yy >= e.height) continue;
        const i = (yy * e.width + xx) * 4, p = (y * canvas.width + x) * 4;
        const a = source.data[p + 3] / 255 * this.globalAlpha, b = cible[i + 3] / 255;
        if (this.globalCompositeOperation === 'multiply') {
          cible.set(multiplierPixel(cible.slice(i, i + 4), [...source.data.slice(p, p + 3), a]), i); continue;
        }
        const alpha = a + b * (1 - a);
        for (let c = 0; c < 3; c++) cible[i + c] = alpha ? (source.data[p + c] * a + cible[i + c] * b * (1 - a)) / alpha : 0;
        cible[i + 3] = alpha * 255;
      }
    },
    getImageData(x, y, width, height) {
      const data = new Uint8ClampedArray(width * height * 4), source = donnees();
      for (let yy = 0; yy < height; yy++) for (let xx = 0; xx < width; xx++) {
        data.set(source.subarray(((y + yy) * e.width + x + xx) * 4, ((y + yy) * e.width + x + xx) * 4 + 4), (yy * width + xx) * 4);
      }
      return { data, width, height };
    },
    putImageData(image, x, y) {
      const cible = donnees();
      for (let yy = 0; yy < image.height; yy++) for (let xx = 0; xx < image.width; xx++) {
        const i = (yy * image.width + xx) * 4;
        cible.set(image.data.subarray(i, i + 4), ((y + yy) * e.width + x + xx) * 4);
      }
    }
  };
  e.getContext = () => ctx; e.toDataURL = () => 'data:image/png;base64,test'; return e;
}
const main = element('main');
globalThis.document = { createElement: element, querySelector: () => main, body: element('body') };
globalThis.ImageData = class { constructor(data, width, height) { Object.assign(this, { data, width, height }); } };
const stockage = new Map();
globalThis.localStorage = { getItem: cle => stockage.get(cle) ?? null, setItem: (cle, valeur) => stockage.set(cle, valeur) };

function contexte() {
  const doc = new DocumentAtelier(), source = creerRaster(11, 11, 'Scan'); source.x = 17; source.y = -3;
  const image = source.ctx2d.getImageData(0, 0, 11, 11); image.data.fill(255);
  for (let y = 2; y <= 8; y++) for (let x = 2; x <= 8; x++) {
    if (x === 2 || x === 8 || y === 2 || y === 8) image.data.set([0, 0, 0, 255], (y * 11 + x) * 4);
  }
  source.ctx2d.putImageData(image, 0, 0); doc.calques = [source]; doc.actifId = source.id;
  const ctx = { document: doc, historique: new Historique(), couleur: [240, 100, 50, 0.5],
    get calqueActif() { return doc.calqueActif; },
    vue: { zone: element('zone'), coordonnees: e => ({ x: e.x, y: e.y }) },
    message(texte) { this.dernierMessage = texte; }, notifier: () => doc.notifier() };
  return { ctx, doc, source };
}

test('Worker réel : cache du masque, invalidation par clé et extraction', async () => {
  const requete = (cle, valeur) => ({ type: 'pot', cle, rgba: new Uint8ClampedArray([valeur, valeur, valeur, 255]),
    largeur: 1, hauteur: 1, x: 0, y: 0, options: { automatique: false, seuil: 128, rayon: 0, tolerance: 32 } });
  assert.ok((await calculer(requete('a', 255))).boite);
  assert.equal((await calculer(requete('a', 255))).cacheUtilise, true);
  const modifie = await calculer(requete('a', 0));
  assert.equal(modifie.boite, null); assert.equal(modifie.cacheUtilise, false);
  assert.equal((await calculer(requete('b', 0))).boite, null);
  const palette = await calculer({ type: 'palette', rgba: new Uint8ClampedArray([255, 0, 0, 255]), options: { n: 3 } });
  assert.deepEqual(palette, [{ r: 255, g: 0, b: 0, part: 1 }]);
});
test('Pot : décalage, couleur alpha, réutilisation, annuler/rétablir et région bornée', async () => {
  const { ctx, doc, source } = contexte(), clic = { button: 0, x: 22, y: 2 };
  await appliquerPot(ctx, clic);
  assert.match(ctx.dernierMessage, /Zone remplie/); assert.equal(doc.calques.length, 2);
  const couleurs = doc.calqueActif;
  assert.equal(couleurs.fusion, 'multiply'); assert.equal(couleurs.sourceId, source.id);
  assert.equal(couleurs.x, 17); assert.equal(couleurs.y, -3);
  assert.deepEqual([...couleurs.ctx2d.getImageData(5, 5, 1, 1).data], [240, 100, 50, 128]);
  assert.deepEqual([...couleurs.ctx2d.getImageData(0, 0, 1, 1).data], [0, 0, 0, 0]);
  assert.equal(ctx.occupe, false); assert.equal(main.inert, false);
  await appliquerPot(ctx, clic); assert.equal(doc.calques.length, 2);
  ctx.historique.annuler(); ctx.historique.annuler(); assert.equal(doc.calques.length, 1); assert.equal(doc.actifId, source.id);
  ctx.historique.retablir(); assert.equal(doc.calques.length, 2); assert.equal(doc.actifId, couleurs.id);
  assert.deepEqual([...couleurs.ctx2d.getImageData(5, 5, 1, 1).data], [240, 100, 50, 128]);
  await appliquerPot(ctx, { button: 0, x: 18, y: -2 });
  assert.equal(doc.calques.length, 2);
});
test('Pot en mode direct multiplie les pixels et reste annulable', async () => {
  const panneau = pot.panneauOptions();
  const cases = panneau.children.flatMap(label => label.children ?? []).filter(input => input.type === 'checkbox');
  const multiplication = cases.at(-1); multiplication.checked = false; multiplication.onchange();
  try {
    const { ctx, doc, source } = contexte(); ctx.couleur = [200, 100, 50, 1];
    await appliquerPot(ctx, { button: 0, x: 22, y: 2 });
    assert.equal(doc.calques.length, 1);
    assert.deepEqual([...source.ctx2d.getImageData(5, 5, 1, 1).data], [200, 100, 50, 255]);
    ctx.historique.annuler(); assert.deepEqual([...source.ctx2d.getImageData(5, 5, 1, 1).data], [255, 255, 255, 255]);
  } finally { multiplication.checked = true; multiplication.onchange(); }
});
test('Pipette active convertit le décalage et ignore les clics hors calque', () => {
  const { ctx } = contexte(); let couleur;
  ctx.definirCouleur = valeur => { couleur = valeur; };
  prelever(ctx, { x: 22, y: 2 }, false); assert.deepEqual(couleur, [255, 255, 255, 1]);
  prelever(ctx, { x: -10, y: -10 }, false); assert.deepEqual(couleur, [255, 255, 255, 1]);
});
test('Pipette composée, Alt+clic et source visible respectent les décalages', async () => {
  const { ctx, doc } = contexte(), superpose = creerRaster(1, 1, 'Trait superposé');
  doc.largeur = 40; doc.hauteur = 40; superpose.x = 22; superpose.y = 2;
  superpose.ctx2d.putImageData({ data: new Uint8ClampedArray([0, 0, 0, 255]), width: 1, height: 1 }, 0, 0);
  doc.calques.push(superpose); let couleur;
  ctx.definirCouleur = valeur => { couleur = valeur; };
  prelever(ctx, { x: 22, y: 2 }, true); assert.deepEqual(couleur, [0, 0, 0, 1]);
  await appliquerPot(ctx, { button: 0, altKey: true, x: 22, y: 2 });
  assert.deepEqual(couleur, [0, 0, 0, 1]); assert.equal(ctx.historique.passes.length, 0);
  const panneau = pot.panneauOptions(), select = panneau.children.flatMap(e => e.children ?? []).find(e => e.tag === 'select');
  select.value = 'visibles'; select.onchange();
  try {
    await appliquerPot(ctx, { button: 0, x: 22, y: 2 });
    assert.match(ctx.dernierMessage, /Zone vide/); assert.equal(doc.calques.length, 2);
  } finally { select.value = 'actif'; select.onchange(); }
});
test('Palette : extraction hors fil, pastilles accessibles, récentes sans doublons et stockage', async () => {
  const { ctx, doc } = contexte(), panneau = element('section'), input = element('input'), alpha = element('input');
  installerPalette(ctx, panneau, input, alpha);
  ctx.definirCouleur([255, 0, 0, 1]); ctx.definirCouleur([255, 0, 0, 1]);
  assert.deepEqual(doc.recentes, ['#ff0000']); assert.equal(input.value, '#ff0000');
  for (let i = 0; i < 20; i++) ctx.definirCouleur([i, 0, 0, 1]);
  assert.equal(doc.recentes.length, 12);
  assert.deepEqual(JSON.parse(stockage.get('atelier.couleurs-recentes')), doc.recentes);
  const extraire = panneau.children.find(e => e.tag === 'button');
  // Le faux select reproduit ici la sélection automatique du premier élément du navigateur.
  panneau.children[1].children[1].value = doc.actifId;
  await extraire.onclick(); assert.deepEqual(doc.palette, []);
  const options = panneau.children[2].children;
  const ignorer = options[1].children[0]; ignorer.checked = false; ignorer.onchange();
  await extraire.onclick(); assert.equal(doc.palette.length, 2);
  const pastilles = panneau.children.find(e => e.className === 'pastilles');
  assert.ok(pastilles.children.every(b => /^#[0-9a-f]{6}$/.test(b['aria-label'])));
  pastilles.children[0].onclick(); assert.equal(input.value, pastilles.children[0]['aria-label']);
});
test('Projet : palette facultative, nettoyage, limites et lien source', async () => {
  const doc = new DocumentAtelier();
  doc.palette = ['#AABBCC', '#aabbcc', 'invalide']; doc.recentes = ['#ff0000'];
  const c = { id: 'e', nom: 'Élément', type: 'element', visible: true, opacite: 1, fusion: 'multiply', x: 17, y: -3, sourceId: 'dessin' };
  doc.calques = [c]; const json = serialiser(doc), etat = await deserialiser(json);
  assert.deepEqual(etat.palette, ['#aabbcc']); assert.deepEqual(etat.recentes, ['#ff0000']);
  assert.equal(etat.calques[0].sourceId, 'dessin');
  delete json.palette; delete json.recentes;
  const ancien = await deserialiser(json); assert.deepEqual(ancien.palette, []); assert.deepEqual(ancien.recentes, []);
  assert.deepEqual(nettoyerCouleurs(null), []);
});

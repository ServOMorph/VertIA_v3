import test from 'node:test';
import assert from 'node:assert/strict';
import { DocumentAtelier, composer, enregistrerRendu } from '../static/js/document.js';
import { Historique, MAX_PAS, instantaneRegion } from '../static/js/historique.js';
import { serialiser, deserialiser } from '../static/js/projet.js';

test('Les changements de calques restent cohérents après annulation et nouvelle branche', () => {
  const doc = new DocumentAtelier(), historique = new Historique();
  const calque = { id: 'a', nom: 'Scan', visible: true };
  doc.transaction(historique, 'Import', () => { doc.calques.push(calque); doc.actifId = calque.id; });
  doc.modifier(historique, calque, { nom: 'Mandala', visible: false }, 'Propriétés');
  doc.transaction(historique, 'Suppression', () => { doc.calques = []; doc.actifId = null; });
  historique.annuler(); historique.annuler();
  assert.equal(doc.calqueActif.nom, 'Scan'); assert.equal(doc.calqueActif.visible, true);
  historique.annuler(); assert.equal(doc.calques.length, 0);
  historique.retablir(); historique.retablir();
  assert.equal(doc.calqueActif.nom, 'Mandala');
  doc.modifier(historique, calque, { visible: true }, 'Afficher');
  historique.retablir(); assert.equal(doc.calques.length, 1);
  assert.equal(historique.futurs.length, 0);
});

test('Historique borné et restauration de la seule région de pixels', () => {
  const historique = new Historique(); let valeur = 0;
  for (let i = 0; i < 45; i++) {
    const avant = valeur++; const apres = valeur;
    historique.enregistrer({ annuler: () => { valeur = avant; }, retablir: () => { valeur = apres; } });
  }
  assert.equal(historique.passes.length, MAX_PAS);
  for (let i = 0; i < 45; i++) historique.annuler();
  assert.equal(valeur, 5);
  let pixels = 'avant'; const lectures = [], ecritures = [];
  const calque = { canvas: { width: 6000, height: 6000 }, ctx2d: {
    getImageData(...zone) { lectures.push(zone); return pixels; },
    putImageData(...args) { ecritures.push(args); }
  } };
  const capture = instantaneRegion(calque, -2, 20, 12, 15);
  pixels = 'apres'; const action = capture.terminer();
  action.annuler(); action.retablir();
  assert.deepEqual(lectures, [[0, 20, 10, 15], [0, 20, 10, 15]]);
  assert.deepEqual(ecritures, [['avant', 0, 20], ['apres', 0, 20]]);
});

test('Un futur élément conserve ses données et utilise son rendu enregistré', async () => {
  const doc = new DocumentAtelier();
  doc.calques = [{ id: 'e', nom: 'Élément', type: 'element', visible: true,
    opacite: 0.4, fusion: 'multiply', x: 10, y: 20, donnees: { texte: 'Exemple' } }];
  const etat = await deserialiser(serialiser(doc));
  assert.deepEqual(etat.calques, doc.calques);
  const appels = [];
  enregistrerRendu('element', (ctx, calque) => appels.push([ctx.globalAlpha, ctx.globalCompositeOperation, calque.donnees]));
  const ctx = { save() {}, restore() {}, translate(x, y) { appels.push([x, y]); } };
  composer(ctx, etat);
  assert.deepEqual(appels, [[10, 20], [0.4, 'multiply', { texte: 'Exemple' }]]);
  await assert.rejects(() => deserialiser({ format: 'atelier', version: 2 }));
});

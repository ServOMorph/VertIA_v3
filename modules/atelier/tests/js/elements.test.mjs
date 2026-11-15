import test from 'node:test';
import assert from 'node:assert/strict';
import { interpolerTampons } from '../../static/js/outils/pinceau.js';
import { creerElement, boiteElement, validerElement } from '../../static/js/elements/registre.js';
import { poignees, toucherPoignee, redimensionner, depuisGlissement, contient } from '../../static/js/elements/geometrie.js';
import { serialiser, deserialiser } from '../../static/js/projet.js';
import { DocumentAtelier, creerCalqueElement, composer } from '../../static/js/document.js';
import { Historique } from '../../static/js/historique.js';
import selection from '../../static/js/outils/selection.js';
import { ajouterElement, supprimerSelection } from '../../static/js/outils/elements.js';

test('Tampons : pas au plus égal au quart de la taille, dernier point exact et absence de trou', () => {
  for (const taille of [1, 3, 30, 300]) for (const fin of [{ x: 121, y: -93 }, { x: 0, y: 0 }, { x: 0.01, y: 0.04 }]) {
    let precedent = { x: 0, y: 0 };
    const points = interpolerTampons(precedent, fin, taille);
    for (const p of points) {
      assert.ok(Math.hypot(p.x - precedent.x, p.y - precedent.y) <= taille / 4 + 1e-10);
      precedent = p;
    }
    assert.deepEqual(points.at(-1), fin);
  }
});

test('Boîtes de tous les éléments, poignées aux quatre coins et détection à zoom variable', () => {
  for (const type of ['texte', 'rectangle', 'ellipse']) {
    const e = creerElement(type, { x: 10, y: 20, largeur: 80, hauteur: 40 }), b = boiteElement(e);
    assert.deepEqual(b, { x: 10, y: 20, largeur: 80, hauteur: 40 });
    poignees(b).forEach((p, i) => assert.equal(toucherPoignee(b, p), i));
    assert.equal(toucherPoignee(b, { x: 15, y: 24 }, 6), 0);
    assert.equal(toucherPoignee(b, { x: 15, y: 24 }, 3), -1);
    assert.equal(contient(e, { x: 40, y: 30 }), true);
    assert.equal(contient(e, { x: -1, y: 30 }), false);
  }
  const ligne = creerElement('ligne', { x: 90, y: 60, x2: 10, y2: 20 });
  assert.deepEqual(boiteElement(ligne), { x: 10, y: 20, largeur: 80, hauteur: 40 });
  assert.equal(contient(ligne, { x: 50, y: 40 }), true);
  assert.equal(contient(ligne, { x: 50, y: 20 }, 2), false);
});

test('Redimensionnement depuis chaque poignée : coin opposé fixe, Maj conserve les proportions', () => {
  const e = creerElement('rectangle', { x: 10, y: 20, largeur: 80, hauteur: 40 });
  for (let i = 0; i < 4; i++) {
    const coins = poignees(boiteElement(e)), oppose = coins[(i + 2) % 4];
    const fin = { x: coins[i].x + ([0, 3].includes(i) ? -20 : 20), y: coins[i].y + (i < 2 ? -30 : 30) };
    const libre = redimensionner(e, i, fin), contraint = redimensionner(e, i, fin, true);
    assert.equal(libre.largeur, 100); assert.equal(libre.hauteur, 70);
    assert.ok(poignees(boiteElement(libre)).some(p => p.x === oppose.x && p.y === oppose.y));
    assert.equal(contraint.largeur / contraint.hauteur, 2);
    assert.ok(poignees(boiteElement(contraint)).some(p => p.x === oppose.x && p.y === oppose.y));
  }
  const croise = redimensionner(e, 0, { x: 100, y: 80 });
  assert.deepEqual(boiteElement(croise), { x: 90, y: 60, largeur: 10, hauteur: 20 });
  const ligne = creerElement('ligne', { x: 90, y: 60, x2: 10, y2: 20 });
  const agrandie = redimensionner(ligne, 2, { x: 170, y: 100 }, true);
  assert.deepEqual(boiteElement(agrandie), { x: 10, y: 20, largeur: 160, hauteur: 80 });
  assert.ok(agrandie.x > agrandie.x2 && agrandie.y > agrandie.y2);
  const inverse = redimensionner(ligne, 0, { x: 100, y: 80 });
  assert.deepEqual([inverse.x, inverse.y, inverse.x2, inverse.y2], [90, 60, 100, 80]);
  const horizontale = creerElement('ligne', { x: 10, y: 20, x2: 90, y2: 20 });
  const etiree = redimensionner(horizontale, 1, { x: 120, y: 50 });
  assert.deepEqual([etiree.x, etiree.y, etiree.x2, etiree.y2], [10, 20, 120, 50]);
  assert.equal(redimensionner(horizontale, 1, { x: 120, y: 50 }, true).y2, 20);
  const verticale = creerElement('ligne', { x: 10, y: 20, x2: 10, y2: 100 });
  assert.equal(redimensionner(verticale, 2, { x: 50, y: 120 }, true).x2, 10);
});

test('Glissements inversés, carrés, cercles, lignes à 45 degrés et clic sans étendue', () => {
  for (const type of ['rectangle', 'ellipse']) {
    assert.deepEqual(depuisGlissement(type, { x: 50, y: 50 }, { x: 20, y: 40 }), { x: 20, y: 40, largeur: 30, hauteur: 10 });
    assert.deepEqual(depuisGlissement(type, { x: 50, y: 50 }, { x: 20, y: 40 }, true), { x: 20, y: 20, largeur: 30, hauteur: 30 });
    const nul = depuisGlissement(type, { x: 1, y: 1 }, { x: 1, y: 1 });
    assert.equal(nul.largeur, 1); assert.equal(nul.hauteur, 1);
  }
  const l = depuisGlissement('ligne', { x: 5, y: 6 }, { x: 80, y: 70 }, true);
  assert.ok(Math.abs((l.x2 - l.x) - (l.y2 - l.y)) < 1e-10);
});

test('Projet mixte : aller-retour JSON sans DOM, raster, texte, trois formes et compatibilité A/B', async () => {
  const doc = new DocumentAtelier();
  const raster = { id: 'scan', nom: 'Scan', type: 'raster', visible: true, opacite: 1, fusion: 'source-over', x: -20, y: 30,
    canvas: { toDataURL: () => 'data:image/png;base64,pixels' } };
  doc.calques = [raster, ...['texte', 'rectangle', 'ellipse', 'ligne'].map(type => creerCalqueElement(creerElement(type)))];
  doc.calques[1].donnees.contenu = 'Été\nDeuxième ligne';
  doc.calques[2].opacite = 0.4; doc.calques[2].fusion = 'multiply'; doc.calques[2].sourceId = 'scan';
  doc.palette = ['#aabbcc']; doc.recentes = ['#123456'];
  const json = serialiser(doc), charge = await deserialiser(JSON.parse(JSON.stringify(json)), async source => {
    assert.equal(source, 'data:image/png;base64,pixels'); return { canvas: raster.canvas };
  });
  assert.deepEqual(serialiser(charge), json);
  assert.equal(charge.calques[1].donnees.contenu, 'Été\nDeuxième ligne');
  assert.equal(charge.calques[2].sourceId, 'scan');
  json.calques[1].donnees.contenu = 'Modifié'; assert.notEqual(doc.calques[1].donnees.contenu, 'Modifié');
  delete json.palette; delete json.recentes;
  const ancien = await deserialiser(json, async () => ({ canvas: raster.canvas }));
  assert.deepEqual(ancien.palette, []); assert.deepEqual(ancien.recentes, []);
  assert.throws(() => validerElement(creerElement('texte', { police: 'inconnue' })));
  assert.throws(() => validerElement(creerElement('ellipse', { largeur: -1 })));
  assert.throws(() => validerElement(creerElement('ligne', { x2: Infinity })));
});

function contexte() {
  const doc = new DocumentAtelier(), historique = new Historique(() => doc.notifier());
  const ctx = { document: doc, historique, get calqueActif() { return doc.calqueActif; },
    notifier: () => doc.notifier(), vue: { zoom: 0.5, coordonnees: e => ({ x: e.clientX / 0.5, y: e.clientY / 0.5 }) } };
  return ctx;
}
const evenement = (x, y, autres = {}) => ({ clientX: x / 2, clientY: y / 2, button: 0, type: 'pointerup', ...autres });

test('Sélection à zoom 50 %, déplacement et redimensionnement annulables en un pas, annulation du geste', () => {
  const ctx = contexte(), c = ajouterElement(ctx, creerElement('rectangle', { x: 10, y: 20, largeur: 80, hauteur: 40 }));
  c.x = 100; c.y = 200;
  selection.pointeurBas(ctx, evenement(150, 240));
  selection.pointeurDeplace(ctx, evenement(170, 260)); selection.pointeurHaut(ctx, evenement(170, 260));
  assert.equal(c.x, 120); assert.equal(c.y, 220); assert.equal(ctx.historique.passes.length, 2);
  ctx.historique.annuler(); assert.equal(c.x, 100); ctx.historique.retablir(); assert.equal(c.x, 120);
  selection.pointeurBas(ctx, evenement(210, 280)); selection.pointeurHaut(ctx, evenement(290, 320, { shiftKey: true }));
  assert.equal(c.donnees.largeur, 160); assert.equal(c.donnees.hauteur, 80); assert.equal(ctx.historique.passes.length, 3);
  ctx.historique.annuler(); assert.equal(c.donnees.largeur, 80); ctx.historique.retablir(); assert.equal(c.donnees.largeur, 160);
  selection.pointeurBas(ctx, evenement(170, 270)); selection.pointeurDeplace(ctx, evenement(300, 400));
  selection.pointeurHaut(ctx, evenement(300, 400, { type: 'pointercancel' }));
  assert.equal(c.x, 120); assert.equal(ctx.historique.passes.length, 3);
  supprimerSelection(ctx); assert.equal(ctx.document.calques.length, 0);
  ctx.historique.annuler(); assert.equal(ctx.calqueActif, c);
  ctx.document.modifier(ctx.historique, c, { donnees: { ...c.donnees, couleur: '#ff0000' } }, 'Couleur');
  ctx.historique.annuler(); assert.equal(c.donnees.couleur, '#000000');
  ctx.historique.retablir(); assert.equal(c.donnees.couleur, '#ff0000');
});

test('Au moins trente modifications vectorielles restaurables', () => {
  const ctx = contexte(), c = ajouterElement(ctx, creerElement('texte'));
  for (let i = 1; i <= 35; i++) ctx.document.modifier(ctx.historique, c, { donnees: { ...c.donnees, contenu: String(i) } }, 'Texte');
  for (let i = 0; i < 35; i++) ctx.historique.annuler();
  assert.equal(c.donnees.contenu, 'Texte');
  for (let i = 0; i < 35; i++) ctx.historique.retablir();
  assert.equal(c.donnees.contenu, '35');
});

test('Composition vectorielle : coordonnées et alpha du calque, même rendu à pleine résolution', () => {
  const appels = [], ctx = { save() {}, restore() {}, translate: (...p) => appels.push(p), beginPath() {},
    rect: (...b) => appels.push(b), fill() {}, stroke() { appels.push([this.globalAlpha, this.globalCompositeOperation]); } };
  const c = creerCalqueElement(creerElement('rectangle', { x: 5, y: 6, largeur: 700, hauteur: 500 }));
  Object.assign(c, { x: 10, y: 20, opacite: 0.3, fusion: 'multiply' });
  composer(ctx, { calques: [c] });
  assert.deepEqual(appels, [[10, 20], [5, 6, 700, 500], [0.3, 'multiply']]);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import { DocumentAtelier } from '../../static/js/document.js';
import { Historique } from '../../static/js/historique.js';
import { ajouterHistorique, bornerZone, creerDialogue, deplacerZone, poignee, redimensionnerZone,
  zoneAvecMarge } from '../../static/js/outils/dialogue.js';

test('Calcul des marges, bornes, dimensions minimales et déplacement', () => {
  assert.deepEqual(zoneAvecMarge([4, 8, 17, 20], 18, 36), [0, 5, 18, 23]);
  assert.deepEqual(zoneAvecMarge([10, 10, 30, 30], 40, 40, .5), [0, 0, 40, 40]);
  assert.deepEqual(bornerZone([43, 39, 45, 38], 40, 40), [32, 32, 40, 40]);
  assert.deepEqual(bornerZone([14, 13, -1, -2], 40, 40), [0, 0, 14, 13]);
  assert.deepEqual(bornerZone([0, 0, 0, 0], 3, 5), [0, 0, 3, 5]);
  assert.equal(bornerZone(null, 40, 40), null);
  assert.deepEqual(deplacerZone([1, 3, 15, 18], 100, -100, 40, 40), [26, 0, 40, 15]);
});

test('Les quatre poignées laissent le coin opposé en place', () => {
  const zone = [10, 20, 40, 60];
  const coins = [[10, 20], [40, 20], [40, 60], [10, 60]];
  coins.forEach(([x, y], i) => assert.equal(poignee(zone, { x: x + 1, y }, 2), i));
  assert.equal(poignee(zone, { x: 25, y: 40 }, 4), -1);
  const point = { x: 15, y: 25 };
  assert.deepEqual(coins.map((_, i) => redimensionnerZone(zone, i, point)), [
    [15, 25, 40, 60], [10, 25, 15, 60], [10, 20, 15, 25], [15, 20, 40, 25]
  ]);
  assert.deepEqual(zone, [10, 20, 40, 60]);
});

test('Historique borné avec question, réponse et titres', () => {
  const ancien = Array.from({ length: 20 }, (_, i) => ({ role: 'user', contenu: String(i) }));
  const nouveau = ajouterHistorique(ancien, 'Quels changements ?', {
    reponse: 'Deux idées.', propositions: [{ titre: 'Ciel' }, { titre: 'Arbre' }]
  });
  assert.equal(nouveau.length, 20);
  assert.equal(nouveau[0].contenu, '2');
  assert.deepEqual(nouveau.slice(-2), [
    { role: 'user', contenu: 'Quels changements ?' },
    { role: 'assistant', contenu: 'Deux idées.\n- Ciel\n- Arbre' }
  ]);
  assert.equal(ancien[0].contenu, '0');
  const longue = ajouterHistorique([], 'Une question ?', {
    reponse: 'a'.repeat(8000), propositions: [{ titre: 'Ciel' }]
  }).at(-1).contenu;
  assert.equal(longue.length, 8000);
  assert.ok(longue.endsWith('\n- Ciel'));
});

function atelier(t, { echec, attente, sansZone = false } = {}) {
  const originaux = { document: globalThis.document, Image: globalThis.Image, fetch: globalThis.fetch };
  t.after(() => Object.assign(globalThis, originaux));
  if (!globalThis.crypto) Object.defineProperty(globalThis, 'crypto', { value: webcrypto, configurable: true });
  const exports = new Map(), requetes = [], verrous = [], messages = [];
  globalThis.document = { createElement(tag) {
    const element = { tag, children: [], style: {}, attributs: {},
      append(...enfants) { this.children.push(...enfants); },
      setAttribute(nom, valeur) { this.attributs[nom] = valeur; } };
    if (tag === 'canvas') {
      const rendu = { dessins: [], rectangles: [], decoupes: [], save() {}, restore() {}, translate() {},
        beginPath() {}, clip() {}, rect(...args) { this.decoupes.push(args); },
        drawImage(...args) { this.dessins.push(args); },
        fillRect(...args) { this.rectangles.push([this.fillStyle, ...args]); } };
      element.getContext = () => rendu;
      element.toDataURL = () => {
        const url = 'data:image/png;base64,faux' + exports.size;
        exports.set(url, element); return url;
      };
    }
    return element;
  } };
  globalThis.Image = class { set src(_) { queueMicrotask(() => this.onload()); } };
  const propositions = [
    { titre: 'Ciel', prompt: 'Bleu', zone: [10, 10, 30, 30] },
    { titre: 'Arbre', prompt: 'Vert', zone: sansZone ? null : [20, 20, 40, 40] }
  ];
  let nombre = 0;
  globalThis.fetch = async (url, options) => {
    const corps = options.body && JSON.parse(options.body);
    requetes.push({ url, methode: options.method, corps });
    let json = { etat: 'termine', message: 'Terminé' };
    if (url === 'api/analyse') json = { id: 'analyse-1' };
    if (url === 'api/analyse/analyse-1/resultat') json = { reponse: 'Deux idées.', propositions };
    if (url === 'api/retouche') {
      nombre++;
      if (attente) await attente;
      json = { id: `zone-${nombre}` };
    } else if (url === `api/retouche/zone-${echec}`) {
      json = { etat: 'echec', message: 'échec du moteur' };
    } else if (attente && url === 'api/retouche/zone-1' && options.method !== 'DELETE') {
      await new Promise((_, reject) => options.signal.addEventListener('abort',
        () => reject(options.signal.reason), { once: true }));
    }
    return { ok: true, json: async () => json, blob: async () => new Blob(['png']) };
  };
  const doc = new DocumentAtelier(), historique = new Historique(), outil = creerDialogue();
  doc.largeur = 60; doc.hauteur = 50;
  doc.calques.push({ id: 'fond', type: 'raster', visible: true, x: 0, y: 0, canvas: 'fond' });
  let panneau;
  const ctx = { document: doc, historique, vue: { zoom: 2, invalider() {}, coordonnees: e => e },
    message: m => messages.push(m), verrouillerRetouche: v => verrous.push(v),
    actualiserOptions() { panneau = outil.panneauOptions(ctx); } };
  ctx.actualiserOptions();
  const elements = (tag, racine = panneau) => [racine, ...racine.children.flatMap(e =>
    typeof e === 'object' ? elements(tag, e) : [])].filter(e => e.tag === tag);
  const bouton = texte => elements('button').find(e => e.textContent === texte);
  const envoyer = () => bouton('Envoyer').onclick();
  const appliquer = () => bouton('Appliquer les zones cochées').onclick();
  return { doc, ctx, outil, requetes, exports, verrous, messages, elements, bouton, envoyer, appliquer, historique };
}

test('Deux zones successives, masques et découpages, un calque historique par résultat', async t => {
  const a = atelier(t);
  await a.envoyer();
  assert.deepEqual(a.requetes[0].corps.historique, []);
  assert.equal(a.requetes[0].corps.prompt, 'Que proposes-tu pour améliorer cette image ?');
  const texte = a.elements('textarea')[1];
  texte.value = 'Bleu clair'; texte.oninput();
  await a.appliquer();
  const zones = a.requetes.filter(r => r.url === 'api/retouche');
  assert.equal(zones.length, 2);
  assert.equal(zones[0].corps.prompt, 'Bleu clair');
  assert.deepEqual([zones[0].corps.force, zones[0].corps.etapes, zones[0].corps.seed], [.85, 20, -1]);
  const images = zones.map(r => a.exports.get(r.corps.image));
  const dessins = images.map(i => i.getContext().dessins[0]);
  assert.deepEqual(dessins[0].slice(1), [5, 5, 30, 30, 0, 0, 30, 30]);
  assert.deepEqual(dessins[1].slice(1), [15, 15, 30, 30, 0, 0, 30, 30]);
  assert.deepEqual(dessins[0][0].getContext().dessins.map(d => d[0]), ['fond']);
  assert.deepEqual(dessins[1][0].getContext().dessins.map(d => d[0]), ['fond', a.doc.calques[1].canvas]);
  assert.deepEqual(a.exports.get(zones[0].corps.masque).getContext().rectangles, [
    ['#000', 0, 0, 30, 30], ['#fff', 5, 5, 20, 20]
  ]);
  assert.deepEqual(a.doc.calques.slice(1).map(c => c.nom), ['Retouche : Ciel', 'Retouche : Arbre']);
  assert.deepEqual(a.doc.calques[1].ctx2d.dessins[0].slice(1), [5, 5, 30, 30]);
  assert.deepEqual(a.doc.calques[1].ctx2d.decoupes, [[5, 5, 30, 30]]);
  assert.deepEqual([a.doc.calques[1].canvas.width, a.doc.calques[1].canvas.height], [60, 50]);
  assert.deepEqual(a.verrous, [true, false, true, false]);
  assert.equal(a.historique.passes.length, 2);
  a.historique.annuler(); assert.equal(a.doc.calques.at(-1).nom, 'Retouche : Ciel');
  a.historique.retablir(); assert.equal(a.doc.calques.at(-1).nom, 'Retouche : Arbre');

  const question = a.elements('textarea')[0];
  question.value = 'Et ensuite ?'; question.oninput();
  await a.envoyer();
  assert.deepEqual(a.requetes.filter(r => r.url === 'api/analyse').at(-1).corps.historique, [
    { role: 'user', contenu: 'Que proposes-tu pour améliorer cette image ?' },
    { role: 'assistant', contenu: 'Deux idées.\n- Ciel\n- Arbre' }
  ]);
});

test('Une erreur de retouche arrête la séquence et libère l’Atelier', async t => {
  const a = atelier(t, { echec: 1 });
  await a.envoyer();
  await a.appliquer();
  assert.equal(a.requetes.filter(r => r.url === 'api/retouche').length, 1);
  assert.equal(a.doc.calques.length, 1);
  assert.match(a.messages.at(-1), /Ciel.*échec du moteur/);
  assert.equal(a.verrous.at(-1), false);
});

test('Annuler pendant le POST envoie DELETE dès la prise en charge et arrête la séquence', async t => {
  let reprendre;
  const attente = new Promise(resolve => { reprendre = resolve; });
  const a = atelier(t, { attente });
  await a.envoyer();
  const sequence = a.appliquer(), annulation = a.bouton('Annuler').onclick();
  reprendre();
  await Promise.all([sequence, annulation]);
  assert.equal(a.requetes.filter(r => r.url === 'api/retouche').length, 1);
  assert.deepEqual(a.requetes.at(-1), { url: 'api/retouche/zone-1', methode: 'DELETE', corps: undefined });
  assert.equal(a.doc.calques.length, 1);
  assert.equal(a.messages.at(-1), 'Annulé');
  assert.equal(a.verrous.at(-1), false);
});

test('Le canevas déplace, redimensionne et trace les zones en pixels natifs', async t => {
  const a = atelier(t, { sansZone: true });
  await a.envoyer();
  assert.equal(a.elements('input')[1].checked, false);
  const glisser = (x, y, finX, finY) => {
    a.outil.pointeurBas(a.ctx, { button: 0, x, y });
    a.outil.pointeurHaut(a.ctx, { type: 'pointerup', x: finX, y: finY });
  };
  glisser(20, 20, 25, 25);
  glisser(35, 35, 100, 100);
  a.bouton('2. Arbre').onclick();
  glisser(9, 8, 3, 2);
  assert.equal(a.elements('input')[1].checked, true);
  await a.appliquer();
  const zones = a.requetes.filter(r => r.url === 'api/retouche');
  const decoupes = zones.map(r => a.exports.get(r.corps.image).getContext().dessins[0].slice(1, 5));
  assert.deepEqual(decoupes, [[3, 6, 57, 44], [1, 0, 12, 12]]);
});

test('zoneDessin : zone élargie de la marge d’adoucissement, bornée au découpage', async () => {
  const { zoneDessin } = await import('../../static/js/outils/dialogue.js');
  assert.deepEqual(zoneDessin([100, 100, 200, 200], { x: 75, y: 75, largeur: 150, hauteur: 150 }), [93, 93, 207, 207]);
  assert.deepEqual(zoneDessin([0, 0, 40, 40], { x: 0, y: 0, largeur: 50, hauteur: 50 }), [0, 0, 47, 47]);
  assert.deepEqual(zoneDessin([500, 500, 2500, 2500], { x: 0, y: 0, largeur: 3000, hauteur: 3000 }), [463, 463, 2537, 2537]);
});

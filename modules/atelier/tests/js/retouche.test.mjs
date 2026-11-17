import test from 'node:test';
import assert from 'node:assert/strict';
import { creerMasque, peindreMasque, inverserMasque, pixelsMasque, creerSuivi, ajouterRetouche, creerRetouche } from '../../static/js/outils/retouche.js';
import { DocumentAtelier } from '../../static/js/document.js';
import { Historique } from '../../static/js/historique.js';

test('Masque : dimensions, peinture, gomme, inversion et RGBA gris ou rouge', () => {
  assert.throws(() => creerMasque(0, 2)); assert.throws(() => creerMasque(1.5, 2));
  const masque = creerMasque(5, 3);
  assert.equal(masque.pixels.length, 15); assert.equal(masque.pixels.some(Boolean), false);
  peindreMasque(masque, { x: 2.5, y: 1.5 }, 1);
  assert.deepEqual([...masque.pixels], [0, 0, 0, 0, 0, 0, 0, 255, 0, 0, 0, 0, 0, 0, 0]);
  assert.deepEqual([...pixelsMasque(masque).slice(28, 32)], [255, 255, 255, 255]);
  assert.deepEqual([...pixelsMasque(masque, true).slice(28, 32)], [255, 0, 0, 115]);
  assert.deepEqual([...pixelsMasque(masque, true).slice(0, 4)], [255, 0, 0, 0]);
  inverserMasque(masque); assert.equal(masque.pixels[7], 0); assert.equal(masque.pixels[0], 255);
  inverserMasque(masque); peindreMasque(masque, { x: 2.5, y: 1.5 }, 1, true);
  assert.equal(masque.pixels.some(Boolean), false);
  peindreMasque(masque, { x: -100, y: -100 }, 3); assert.equal(masque.pixels.some(Boolean), false);
});

test('Résultat : un calque supérieur, une action annulable et rétablissable', () => {
  const doc = new DocumentAtelier(), historique = new Historique();
  doc.calques.push({ id: 'fond' }); doc.actifId = 'fond';
  const calque = { id: 'retouche' };
  ajouterRetouche(doc, historique, calque);
  assert.equal(doc.calques.at(-1), calque); assert.equal(calque.nom, 'Retouche IA');
  assert.equal(historique.passes.length, 1);
  historique.annuler(); assert.equal(doc.calques.length, 1); assert.equal(doc.actifId, 'fond');
  historique.retablir(); assert.equal(doc.calques.at(-1), calque); assert.equal(doc.actifId, 'retouche');
});

function scenario(etats) {
  const appels = [], minuteries = new Map(), notifications = [], resultats = [];
  let compteur = 0;
  const suivi = creerSuivi({
    fetcher: async (url, options) => {
      appels.push([url, options]);
      return { ok: true, json: async () => url === 'api/retouche' ? { id: 'abc' } : etats.shift(), blob: async () => 'PNG' };
    },
    programmer: (fn, delai) => { const id = ++compteur; minuteries.set(id, [fn, delai]); return id; },
    deprogrammer: id => minuteries.delete(id),
    notifier: etat => notifications.push(etat), resultat: async blob => resultats.push(blob)
  });
  return { suivi, appels, minuteries, notifications, resultats, async avancer() {
    const [id, [fn, delai]] = minuteries.entries().next().value;
    assert.equal(delai, 3000); minuteries.delete(id); await fn();
  } };
}

test('Envoi, interrogation espacée de 3 s, réception unique et fin des minuteries', async () => {
  const s = scenario([{ etat: 'attente' }, { etat: 'en_cours' }, { etat: 'termine' }]);
  const donnees = { image: 'image', masque: 'masque', prompt: 'Ciel', force: .85 };
  await s.suivi.lancer(donnees);
  assert.deepEqual(JSON.parse(s.appels[0][1].body), donnees);
  await s.avancer(); await s.avancer();
  assert.deepEqual(s.resultats, ['PNG']); assert.equal(s.minuteries.size, 0);
  assert.equal(s.notifications.at(-1).etat, 'termine');
  assert.deepEqual(s.appels.map(a => a[0]), ['api/retouche', 'api/retouche/abc', 'api/retouche/abc', 'api/retouche/abc', 'api/retouche/abc/resultat']);
});

test('Annulation et fermeture arrêtent les minuteries', async () => {
  const s = scenario([{ etat: 'en_cours' }]);
  await s.suivi.lancer({}); await s.suivi.annuler();
  assert.equal(s.appels.at(-1)[1].method, 'DELETE');
  assert.equal(s.notifications.at(-1).etat, 'annule'); assert.equal(s.minuteries.size, 0);
  const ferme = scenario([{ etat: 'attente' }]);
  await ferme.suivi.lancer({}); ferme.suivi.arreter(); assert.equal(ferme.minuteries.size, 0);
});

test('Erreur serveur ou réseau : état explicite et aucun nouveau sondage', async () => {
  for (const fetcher of [async () => ({ ok: false, status: 409, json: async () => ({ detail: 'GPU occupé' }) }), async () => { throw new Error('Réseau'); }]) {
    const notifications = [];
    const suivi = creerSuivi({ fetcher, notifier: e => notifications.push(e), programmer: () => assert.fail('Minuterie inattendue') });
    await suivi.lancer({}); assert.equal(notifications.at(-1).etat, 'echec');
    assert.match(notifications.at(-1).message, /GPU occupé|Réseau/);
  }
  const s = scenario([{ etat: 'echec', message: 'échec du moteur' }]);
  await s.suivi.lancer({}); assert.equal(s.minuteries.size, 0); assert.equal(s.resultats.length, 0);
});

test('Fermeture pendant une réponse : aucun sondage ni résultat tardif', async () => {
  let resoudre; const notifications = [];
  const suivi = creerSuivi({ fetcher: () => new Promise(resolve => { resoudre = resolve; }),
    notifier: e => notifications.push(e), programmer: () => assert.fail('Minuterie tardive') });
  const lancement = suivi.lancer({}); suivi.arreter();
  resoudre({ ok: true, json: async () => ({ id: 'tardif' }) }); await lancement;
  assert.equal(notifications.length, 1);
});

test('Outil : masque vide refuse l’envoi et les gestes restent hors historique', async () => {
  const elements = [];
  globalThis.document = { createElement(tag) {
    const e = { tag, children: [], append(...enfants) { this.children.push(...enfants); }, setAttribute() {} };
    elements.push(e); return e;
  } };
  const messages = [], doc = new DocumentAtelier(), historique = new Historique(); doc.largeur = 5; doc.hauteur = 3;
  const ctx = { document: doc, historique, vue: { invalider() {}, coordonnees: e => e }, message: m => messages.push(m) };
  const outil = creerRetouche(); outil.activer(ctx); outil.panneauOptions(ctx);
  await elements.find(e => e.textContent === 'Lancer').onclick();
  assert.match(messages.at(-1), /masque/);
  outil.pointeurBas(ctx, { button: 0, x: 2, y: 1 }); outil.pointeurHaut(ctx, { type: 'pointerup', x: 2, y: 1 });
  assert.equal(historique.passes.length, 0); assert.equal(doc.calques.length, 0);
  doc.restaurer(doc.etat()); outil.panneauOptions(ctx);
  await elements.findLast(e => e.textContent === 'Lancer').onclick();
  assert.match(messages.at(-1), /Décrivez/);
  elements.find(e => e.textContent === 'Effacer le masque').onclick();
  await elements.find(e => e.textContent === 'Lancer').onclick(); assert.match(messages.at(-1), /masque/);
});

test('Outil complet : composition visible, masque gris à la taille native, réception et historique', async t => {
  const originaux = { document: globalThis.document, Image: globalThis.Image, fetch: globalThis.fetch };
  t.after(() => Object.assign(globalThis, originaux));
  const elements = [], exports = [], copies = [];
  globalThis.document = { createElement(tag) {
    const e = { tag, children: [], append(...enfants) { this.children.push(...enfants); }, setAttribute() {} };
    if (tag === 'canvas') {
      const appels = [], rendu = { save() {}, restore() {}, translate() {},
        drawImage(...args) { appels.push(args); copies.push(args); },
        createImageData: (w, h) => ({ data: new Uint8ClampedArray(w * h * 4) }),
        putImageData(image) { e.pixels = image.data; } };
      e.getContext = () => rendu;
      e.toDataURL = () => { exports.push({ largeur: e.width, hauteur: e.height, appels, pixels: e.pixels }); return 'data:image/png;base64,faux'; };
    }
    elements.push(e); return e;
  } };
  globalThis.Image = class { set src(v) { queueMicrotask(() => this.onload()); } };
  const requetes = [];
  globalThis.fetch = async (url, options) => {
    requetes.push([url, options]);
    return { ok: true, json: async () => url === 'api/retouche' ? { id: 'test' } : { etat: 'termine', message: 'Terminé' }, blob: async () => new Blob(['png']) };
  };
  const doc = new DocumentAtelier(), historique = new Historique(); doc.largeur = 7; doc.hauteur = 5;
  const calque = (id, visible) => ({ id, type: 'raster', canvas: id, visible, opacite: .5, fusion: 'multiply', x: 2, y: 1 });
  doc.calques.push(calque('visible', true), calque('cache', false));
  const occupations = [], ctx = { document: doc, historique, message() {}, verrouillerRetouche: v => occupations.push(v),
    vue: { invalider() {}, coordonnees: e => e } };
  const outil = creerRetouche(); outil.activer(ctx); outil.panneauOptions(ctx);
  outil.pointeurBas(ctx, { button: 0, x: 3, y: 2 }); outil.pointeurHaut(ctx, { type: 'pointerup', x: 3, y: 2 });
  const texte = elements.find(e => e.tag === 'textarea'); texte.value = 'Un ciel bleu'; texte.oninput();
  await elements.find(e => e.textContent === 'Lancer').onclick();
  assert.deepEqual(exports.map(e => [e.largeur, e.hauteur]), [[7, 5], [7, 5]]);
  assert.deepEqual(exports[0].appels.map(a => a[0]), ['visible']);
  for (let i = 0; i < exports[1].pixels.length; i += 4) {
    const p = exports[1].pixels.slice(i, i + 4); assert.equal(p[0], p[1]); assert.equal(p[1], p[2]); assert.equal(p[3], 255);
  }
  assert.equal(JSON.parse(requetes[0][1].body).prompt, 'Un ciel bleu');
  assert.deepEqual(occupations, [true, false]);
  assert.equal(doc.calques.at(-1).nom, 'Retouche IA');
  assert.deepEqual([doc.calques.at(-1).canvas.width, doc.calques.at(-1).canvas.height], [7, 5]);
  assert.equal(historique.passes.length, 1); historique.annuler(); assert.equal(doc.calques.length, 2);
  historique.retablir(); assert.equal(doc.calques.length, 3);
});

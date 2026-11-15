import test from 'node:test';
import assert from 'node:assert/strict';
import { creerPinceau } from '../../static/js/outils/pinceau.js';
import { creerRaster, DocumentAtelier } from '../../static/js/document.js';
import { Historique } from '../../static/js/historique.js';

function element(tag) {
  const e = { children: [], style: {}, append(...enfants) { this.children.push(...enfants); } };
  if (tag !== 'canvas') return e;
  const pile = [];
  const ctx = { globalAlpha: 1, globalCompositeOperation: 'source-over', version: 0, copies: [], lectures: [], gradients: [],
    save() { pile.push([this.globalAlpha, this.globalCompositeOperation]); },
    restore() { [this.globalAlpha, this.globalCompositeOperation] = pile.pop(); },
    beginPath() {}, arc() {}, fill() {}, clearRect() {},
    createRadialGradient(...args) {
      const gradient = { args, stops: [], addColorStop(...stop) { this.stops.push(stop); } };
      this.gradients.push(gradient); return gradient;
    },
    drawImage(...args) { this.copies.push({ args, alpha: this.globalAlpha, fusion: this.globalCompositeOperation }); this.version++; },
    getImageData(...zone) { this.lectures.push(zone); return { version: this.version }; },
    putImageData(image) { this.version = image.version; }
  };
  e.getContext = () => ctx; return e;
}
globalThis.document = { createElement: element };

function contexte() {
  const doc = new DocumentAtelier(), calque = creerRaster(100, 80); calque.x = 100; calque.y = 200;
  doc.calques = [calque]; doc.actifId = calque.id;
  const ctx = { document: doc, historique: new Historique(() => doc.notifier()), couleur: [120, 80, 40, 0.5],
    get calqueActif() { return doc.calqueActif; }, notifier: () => doc.notifier(),
    vue: { zoom: 0.5, invalider() {}, coordonnees: e => ({ x: e.clientX / 0.5, y: e.clientY / 0.5 }) },
    message(texte) { this.dernierMessage = texte; } };
  return ctx;
}
const ev = (x, y, type = 'pointerup') => ({ button: 0, clientX: x / 2, clientY: y / 2, type });

test('Pinceau : tampon radial, aperçu sans mutation, une composition alpha, région locale et un pas par trait', () => {
  const outil = creerPinceau(), ctx = contexte(), c = ctx.calqueActif;
  const panneau = outil.panneauOptions(), champs = panneau.children.map(l => l.children[1]);
  for (const [input, value] of [[champs[0], 20], [champs[1], 50], [champs[2], 40]]) { input.value = value; input.oninput(); }
  outil.pointeurBas(ctx, ev(110, 220));
  outil.pointeurDeplace(ctx, ev(130, 220)); outil.pointeurDeplace(ctx, ev(110, 220));
  assert.ok(c.apercuCanvas); assert.equal(c.ctx2d.copies.length, 0); assert.equal(ctx.historique.passes.length, 0);
  const preview = c.apercuCanvas.getContext('2d').copies.at(-1);
  assert.equal(preview.alpha, 0.2);
  const masque = preview.args[0], tampon = masque.getContext('2d').copies[0].args[0];
  const gradient = tampon.getContext('2d').gradients[0];
  assert.deepEqual(gradient.args, [10, 10, 5, 10, 10, 10]);
  assert.deepEqual(gradient.stops, [[0, 'rgba(120,80,40,1)'], [1, 'rgba(120,80,40,0)']]);
  outil.pointeurHaut(ctx, ev(140, 220));
  assert.equal(c.apercuCanvas, undefined); assert.equal(c.ctx2d.copies.length, 1);
  assert.equal(c.ctx2d.copies[0].alpha, 0.2); assert.equal(c.ctx2d.copies[0].fusion, 'source-over');
  assert.deepEqual(c.ctx2d.lectures, [[0, 9, 51, 22], [0, 9, 51, 22]]);
  assert.equal(ctx.historique.passes.length, 1);
  ctx.historique.annuler(); assert.equal(c.ctx2d.version, 0);
  ctx.historique.retablir(); assert.equal(c.ctx2d.version, 1);
});

test('Gomme : destination-out, alpha indépendant de la couleur ; annulation et sortie hors calque', () => {
  const outil = creerPinceau(true), ctx = contexte(), c = ctx.calqueActif;
  ctx.couleur[3] = 0;
  outil.pointeurBas(ctx, ev(120, 220)); outil.pointeurHaut(ctx, ev(130, 220));
  assert.equal(c.ctx2d.copies[0].fusion, 'destination-out'); assert.equal(c.ctx2d.copies[0].alpha, 1);
  outil.pointeurBas(ctx, ev(120, 220)); outil.pointeurDeplace(ctx, ev(140, 220));
  outil.pointeurHaut(ctx, ev(140, 220, 'pointercancel'));
  assert.equal(c.apercuCanvas, undefined); assert.equal(c.ctx2d.copies.length, 1);
  assert.equal(ctx.historique.passes.length, 1);
  outil.pointeurBas(ctx, ev(-100, -100)); outil.pointeurHaut(ctx, ev(-90, -90));
  assert.equal(ctx.historique.passes.length, 1); assert.equal(c.ctx2d.copies.length, 1);
  outil.pointeurBas(ctx, ev(120, 220)); outil.desactiver(ctx);
  assert.equal(c.apercuCanvas, undefined); assert.equal(c.ctx2d.copies.length, 1);
});

test('Pinceau ignore un document occupé et refuse de peindre un élément vectoriel', () => {
  const outil = creerPinceau(), ctx = contexte(), c = ctx.calqueActif;
  ctx.occupe = true; outil.pointeurBas(ctx, ev(110, 220)); assert.equal(c.apercuCanvas, undefined);
  ctx.occupe = false; c.type = 'element'; outil.pointeurBas(ctx, ev(110, 220));
  assert.match(ctx.dernierMessage, /raster/); assert.equal(ctx.historique.passes.length, 0);
});

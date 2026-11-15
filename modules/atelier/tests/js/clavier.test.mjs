import test from 'node:test';
import assert from 'node:assert/strict';
import { setImmediate } from 'node:timers/promises';

const ids = new Map(), sauvegardes = [];
function element(tag = 'div') {
  const e = { tag, children: [], listeners: {}, style: {}, dataset: {}, value: '', clientWidth: 1264, clientHeight: 864,
    append(...enfants) { this.children.push(...enfants); }, replaceChildren(...enfants) { this.children = enfants; },
    addEventListener(type, fn) { this.listeners[type] = fn; }, setAttribute(n, v) { this[n] = v; },
    contains(cible) { return this === cible || this.children.some(c => typeof c === 'object' && c.contains?.(cible)); },
    closest() { return ['input', 'textarea', 'select'].includes(this.tag) ? this : null; },
    focus() { document.activeElement = this; this.initial = this.value; },
    blur() {
      document.activeElement = document.body;
      if (this.initial !== this.value) this.onchange?.({ target: this });
    },
    select() {}, click() { return this.onclick?.(); },
    get options() { return this.children; },
    getBoundingClientRect() { return { left: 0, top: 0 }; },
    setPointerCapture() {}, hasPointerCapture() { return false; },
    getContext() { return { fillRect() {} }; }, toDataURL() { return 'data:image/png;base64,test'; }
  };
  return e;
}
globalThis.document = {
  body: element('body'), createElement: element, listeners: {},
  getElementById(id) { if (!ids.has(id)) ids.set(id, element()); return ids.get(id); },
  addEventListener(type, fn) { this.listeners[type] = fn; },
  querySelector() {
    const trouver = e => e.dataset?.editeurTexte !== undefined ? e : e.children?.map(c => typeof c === 'object' && trouver(c)).find(Boolean);
    return trouver(ids.get('options'));
  }
};
document.activeElement = document.body;
globalThis.ResizeObserver = class { observe() {} };
globalThis.requestAnimationFrame = () => {};
globalThis.localStorage = { getItem: () => null, setItem() {} };
globalThis.confirm = () => true;
globalThis.prompt = () => 'Test clavier';
globalThis.fetch = async (url, options) => {
  sauvegardes.push(JSON.parse(options.body)); return { ok: true, json: async () => ({}) };
};
const $ = id => document.getElementById(id);
function touche(key, ctrlKey = false) {
  const e = { key, ctrlKey, target: document.activeElement, preventDefault() { this.prevented = true; } };
  document.listeners.keydown(e); return e;
}
function clicZone(type, x, y) {
  $('zone').listeners[type]({ type, clientX: x, clientY: y, button: 0, pointerId: 1, preventDefault() {} });
}

test('Application : ordre des outils, saisie protégée, validation au clic et Ctrl+Z/Y/S après édition', async () => {
  await import('../../static/js/app.js');
  assert.deepEqual($('outils').children.map(b => b.textContent), ['Déplacer / Sélection', 'Pinceau', 'Gomme', 'Pot de peinture', 'Pipette', 'Texte', 'Formes']);
  $('largeur').value = '1200'; $('hauteur').value = '800';
  $('nouveau-form').listeners.submit({ submitter: { value: 'creer' }, preventDefault() {} });
  touche('t'); clicZone('pointerdown', 100, 100); clicZone('pointerup', 100, 100);
  let editeur = document.querySelector(); assert.equal(editeur.tag, 'textarea'); assert.equal(document.activeElement, editeur);
  editeur.value = 'Bonjour B E G I T U V';
  touche('b'); assert.equal($('outils').children[5]['aria-pressed'], 'true');
  const annuler = touche('z', true); assert.equal(annuler.prevented, true);
  assert.equal(document.querySelector().value, 'Texte');
  touche('y', true); assert.equal(document.querySelector().value, 'Bonjour B E G I T U V');
  editeur = document.querySelector(); editeur.focus(); editeur.value = 'Texte enregistré';
  touche('s', true); await setImmediate();
  assert.equal(sauvegardes.at(-1).calques[1].donnees.contenu, 'Texte enregistré');
  editeur = document.querySelector(); editeur.focus(); editeur.value = 'Validation en cliquant dans le document';
  clicZone('pointerdown', 500, 400); clicZone('pointerup', 500, 400);
  touche('s', true); await setImmediate();
  assert.equal(sauvegardes.at(-1).calques[1].donnees.contenu, 'Validation en cliquant dans le document');
  assert.equal(sauvegardes.at(-1).calques.length, 3);
  for (const [lettre, index] of [['v', 0], ['b', 1], ['e', 2], ['g', 3], ['i', 4], ['t', 5], ['u', 6]]) {
    touche(lettre); assert.equal($('outils').children[index]['aria-pressed'], 'true');
  }
});

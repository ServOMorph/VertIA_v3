import { DocumentAtelier, creerRaster } from './document.js';
import { Historique } from './historique.js';
import { Vue } from './vue.js';
import { installerCalques } from './calques.js';
import { importerImage, installerProjet, exporterPNG } from './projet.js';
import { enregistrerOutil, listerOutils } from './outils/registre.js';
import selection from './outils/selection.js';
import pinceau from './outils/pinceau.js';
import gomme from './outils/gomme.js';
import texte from './outils/texte.js';
import forme from './outils/forme.js';
import pot from './outils/pot.js';
import pipette from './outils/pipette.js';
import { installerPalette } from './palette.js';

const $ = id => document.getElementById(id);
const doc = new DocumentAtelier();
const message = texte => { $('message').textContent = texte; };
const historique = new Historique(() => {
  $('annuler').disabled = !historique.passes.length;
  $('retablir').disabled = !historique.futurs.length;
  doc.notifier();
});
const vue = new Vue(doc, $('zone'), $('affichage'), $('statut'));
const ctx = { document: doc, historique, vue, couleur: [0, 0, 0, 1],
  get calqueActif() { return doc.calqueActif; }, notifier: () => doc.notifier(), message };
// Extension IA : inscrire ici de futurs outils via enregistrerOutil(outil).
// Ils recevront le même ctx et fourniront leurs actions à l'historique ;
// tout futur calcul GPU devra passer par les jobs du portail, hors de ce socle.
enregistrerOutil(selection);
enregistrerOutil(pinceau);
enregistrerOutil(gomme);
enregistrerOutil(pot);
enregistrerOutil(pipette);
enregistrerOutil(texte);
enregistrerOutil(forme);
installerPalette(ctx, $('palette'), $('couleur'), $('alpha'));
let outil = null, pointeur = null;
const boutons = new Map();
ctx.actualiserOptions = () => {
  $('options').replaceChildren();
  const panneau = outil?.panneauOptions?.(ctx); if (panneau) $('options').append(panneau);
};
vue.surimpression = rendu => outil?.dessinerSurimpression?.(ctx, rendu);
let dernierActif = null, dernierElement = null;
doc.abonner(() => {
  const actif = doc.calqueActif;
  if (actif?.id !== dernierActif || actif?.donnees !== dernierElement) {
    dernierActif = actif?.id; dernierElement = actif?.donnees;
    if (pointeur === null && !$('options').contains(document.activeElement)) ctx.actualiserOptions();
  }
});
function selectionner(suivant) {
  if (pointeur !== null || ctx.occupe) return;
  outil?.desactiver?.(ctx); outil = suivant; outil.activer?.(ctx);
  $('zone').style.cursor = outil.curseur ?? 'default';
  ctx.actualiserOptions(); vue.invalider();
  for (const [id, bouton] of boutons) bouton.setAttribute('aria-pressed', String(id === outil.id));
}
for (const candidat of listerOutils()) {
  const bouton = document.createElement('button'); bouton.textContent = candidat.libelle;
  bouton.title = `${candidat.libelle}${candidat.raccourci ? ` (${candidat.raccourci.toUpperCase()})` : ''}`;
  bouton.onclick = () => selectionner(candidat); boutons.set(candidat.id, bouton); $('outils').append(bouton);
}
selectionner(selection);
installerCalques(doc, historique, $('calques'));
const projets = installerProjet(ctx, $('ouvrir-dialogue'));
const proteger = action => async (...args) => {
  if (pointeur !== null || ctx.occupe) return;
  try { await action(...args); } catch (erreur) { message(erreur.message); }
};
let occupation = false;
const fichier = action => proteger(async (...args) => {
  if (occupation) return;
  occupation = true;
  try { await action(...args); } finally { occupation = false; }
});
$('enregistrer').onclick = fichier(() => projets.enregistrer());
$('ouvrir').onclick = fichier(() => projets.ouvrir());
$('exporter').onclick = fichier(() => exporterPNG(doc));
$('annuler').onclick = () => { if (pointeur === null && !occupation && !ctx.occupe) historique.annuler(); };
$('retablir').onclick = () => { if (pointeur === null && !occupation && !ctx.occupe) historique.retablir(); };
$('zoom-plus').onclick = () => vue.zoomer(vue.zoom * 1.25);
$('zoom-moins').onclick = () => vue.zoomer(vue.zoom / 1.25);
$('ajuster').onclick = () => vue.ajuster();
$('zoom-cent').onclick = () => vue.zoomer(1);
$('couleur').oninput = e => {
  const hex = e.target.value;
  ctx.definirCouleur([...[1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16)), Number($('alpha').value) / 100]);
};
$('alpha').oninput = e => { ctx.couleur[3] = Number(e.target.value) / 100; };
$('nouveau').onclick = proteger(() => { if (!occupation) $('nouveau-dialogue').showModal(); });
$('nouveau-form').addEventListener('submit', e => {
  if (e.submitter?.value !== 'creer') return;
  const largeur = Number($('largeur').value), hauteur = Number($('hauteur').value);
  if (![largeur, hauteur].every(v => Number.isInteger(v) && v > 0 && v <= 16384)) { e.preventDefault(); return; }
  if (!confirm('Créer un nouveau document ? Le document actuel sera remplacé.')) { e.preventDefault(); return; }
  const fond = creerRaster(largeur, hauteur, 'Fond blanc');
  fond.ctx2d.fillStyle = '#fff'; fond.ctx2d.fillRect(0, 0, largeur, hauteur);
  doc.restaurer({ largeur, hauteur, calques: [fond], actifId: fond.id, vierge: false });
  historique.vider(); projets.reinitialiser(); vue.ajuster(); message('Nouveau document');
});
const importer = fichier(async fichiers => {
  for (const image of fichiers) await importerImage(image, doc, historique, vue);
  message('Import terminé');
});
$('importer').onclick = () => $('fichier').click();
$('fichier').onchange = async e => { await importer([...e.target.files]); e.target.value = ''; };
$('zone').addEventListener('dragover', e => { e.preventDefault(); });
$('zone').addEventListener('drop', e => { e.preventDefault(); importer([...e.dataTransfer.files]); });
$('zone').addEventListener('pointerdown', e => {
  if (occupation || ctx.occupe || pointeur !== null || ![0, 1].includes(e.button)) return;
  document.activeElement?.blur(); $('zone').focus({ preventScroll: true });
  e.preventDefault(); pointeur = e.pointerId; $('zone').setPointerCapture(pointeur);
  try { Promise.resolve(outil?.pointeurBas?.(ctx, e)).catch(erreur => message(erreur.message)); }
  catch (erreur) { message(erreur.message); }
});
$('zone').addEventListener('pointermove', e => {
  const p = vue.coordonnees(e); $('coordonnees').textContent = `x ${Math.round(p.x)} · y ${Math.round(p.y)}`;
  outil?.survol?.(ctx, e);
  if (e.pointerId === pointeur) outil?.pointeurDeplace?.(ctx, e);
});
$('zone').addEventListener('pointerleave', () => outil?.survol?.(ctx, null));
$('zone').addEventListener('dblclick', e => {
  if (!ctx.occupe && !occupation && pointeur === null) outil?.doubleClic?.(ctx, e);
});
for (const type of ['pointerup', 'pointercancel', 'lostpointercapture']) {
  $('zone').addEventListener(type, e => {
    if (e.pointerId !== pointeur) return;
    outil?.pointeurHaut?.(ctx, e);
    pointeur = null;
    if ($('zone').hasPointerCapture(e.pointerId)) $('zone').releasePointerCapture(e.pointerId);
  });
}
document.addEventListener('keydown', e => {
  if (ctx.occupe) { e.preventDefault(); return; }
  const touche = e.key.toLowerCase();
  if (e.ctrlKey || e.metaKey) {
    if (['z', 'y', 's'].includes(touche)) e.preventDefault();
    if (pointeur !== null || occupation) return;
    if (['z', 'y', 's'].includes(touche)) document.activeElement?.blur();
    if (touche === 'z' && !e.shiftKey) historique.annuler();
    if (touche === 'y' || (touche === 'z' && e.shiftKey)) historique.retablir();
    if (touche === 's') $('enregistrer').click();
    if (['z', 'y', 's'].includes(touche)) ctx.actualiserOptions();
  } else if (!e.altKey) {
    if (e.target.closest('input, textarea, select, [contenteditable="true"]')) return;
    if (pointeur !== null || occupation) return;
    if (outil?.touche?.(ctx, e)) { e.preventDefault(); return; }
    const candidat = listerOutils().find(o => o.raccourci === touche);
    if (candidat) { e.preventDefault(); selectionner(candidat); }
  }
});
historique.vider(); vue.ajuster();

import { creerCalqueElement } from '../document.js';
import { boiteElement } from '../elements/registre.js';
import { contient, poignees } from '../elements/geometrie.js';
import { POLICES } from '../elements/texte.js';
import { versHex } from '../algo/couleur.js';

export function trouverElement(ctx, point, type = null) {
  return [...ctx.document.calques].reverse().find(c => c.type === 'element' && c.visible && c.opacite > 0
    && (!type || c.donnees?.type === type)
    && contient(c.donnees, { x: point.x - c.x, y: point.y - c.y }, 5 / ctx.vue.zoom));
}
export function ajouterElement(ctx, donnees, nom) {
  const calque = creerCalqueElement(donnees, nom);
  ctx.document.transaction(ctx.historique, 'Créer un élément', () => {
    ctx.document.calques.push(calque); ctx.document.actifId = calque.id; ctx.document.vierge = false;
  });
  ctx.actualiserOptions?.(); return calque;
}
export function couleurCourante(ctx) { return versHex(ctx.couleur); }
export function cadreSelection(ctx, rendu) {
  const c = ctx.calqueActif; if (c?.type !== 'element' || !c.visible) return;
  const b = boiteElement(c.donnees); if (!b) return;
  rendu.save(); rendu.translate(c.x, c.y); rendu.strokeStyle = '#2558a5'; rendu.fillStyle = '#fff'; rendu.lineWidth = 1 / ctx.vue.zoom;
  rendu.strokeRect(b.x, b.y, b.largeur, b.hauteur);
  const taille = 8 / ctx.vue.zoom;
  for (const p of poignees(b)) { rendu.fillRect(p.x - taille / 2, p.y - taille / 2, taille, taille); rendu.strokeRect(p.x - taille / 2, p.y - taille / 2, taille, taille); }
  rendu.restore();
}
export function supprimerSelection(ctx) {
  const c = ctx.calqueActif; if (c?.type !== 'element') return false;
  ctx.document.transaction(ctx.historique, 'Supprimer un élément', () => {
    ctx.document.calques = ctx.document.calques.filter(calque => calque !== c);
    ctx.document.actifId = ctx.document.calques.at(-1)?.id ?? null;
  });
  ctx.actualiserOptions?.(); return true;
}
export function champ(panneau, libelle, type, valeur, changer, choix = []) {
  const label = document.createElement('label'), input = document.createElement(type === 'select' ? 'select' : type === 'textarea' ? 'textarea' : 'input');
  label.append(libelle);
  if (type === 'select') for (const [value, texte] of choix.map(v => Array.isArray(v) ? v : [v, v])) {
    const option = document.createElement('option'); option.value = value; option.textContent = texte; input.append(option);
  }
  if (!['select', 'textarea'].includes(type)) input.type = type;
  if (type === 'checkbox') input.checked = valeur; else input.value = valeur;
  if (type === 'number') { input.min = 1; input.max = 1000; }
  input.onchange = () => {
    if (type === 'number' && (!input.checkValidity() || !Number.isFinite(Number(input.value)))) return;
    changer(type === 'checkbox' ? input.checked : type === 'number' ? Number(input.value) : input.value);
  };
  label.append(input); panneau.append(label); return input;
}
export function proprietesElement(ctx, panneau) {
  const c = ctx.calqueActif, e = c?.donnees; if (c?.type !== 'element' || !boiteElement(e)) return;
  const changer = changements => ctx.document.modifier(ctx.historique, c, { donnees: { ...c.donnees, ...changements } }, 'Modifier l’élément');
  if (e.type === 'texte') {
    const texte = champ(panneau, 'Contenu', 'textarea', e.contenu, contenu => changer({ contenu, hauteur: contenu.split('\n').length * c.donnees.taille * 1.2 }));
    texte.dataset.editeurTexte = '';
    champ(panneau, 'Police', 'select', e.police, police => changer({ police }), POLICES);
    champ(panneau, 'Taille (px)', 'number', e.taille, taille => changer({ taille, hauteur: taille * 1.2 * c.donnees.contenu.split('\n').length }));
    champ(panneau, 'Gras', 'checkbox', e.gras, gras => changer({ gras }));
    champ(panneau, 'Italique', 'checkbox', e.italique, italique => changer({ italique }));
    champ(panneau, 'Alignement', 'select', e.alignement, alignement => changer({ alignement }), [['left', 'Gauche'], ['center', 'Centré'], ['right', 'Droite']]);
  } else {
    const epaisseur = champ(panneau, 'Épaisseur (px)', 'number', e.epaisseur, epaisseur => changer({ epaisseur })); epaisseur.max = 300;
    if (e.type !== 'ligne') {
      champ(panneau, 'Remplir', 'checkbox', !!e.remplissage, actif => changer({ remplissage: actif ? couleurCourante(ctx) : null }));
      champ(panneau, 'Remplissage', 'color', e.remplissage ?? '#ffffff', remplissage => changer({ remplissage }));
    }
  }
  champ(panneau, e.type === 'texte' ? 'Couleur' : 'Trait', 'color', e.couleur, couleur => changer({ couleur }));
}
export function editerTexte(ctx) {
  ctx.actualiserOptions?.();
  const champTexte = document.querySelector('[data-editeur-texte]'); champTexte?.focus(); champTexte?.select();
}

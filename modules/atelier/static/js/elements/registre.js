import * as texte from './texte.js';
import * as rectangle from './rectangle.js';
import * as ellipse from './ellipse.js';
import * as ligne from './ligne.js';

const elements = new Map();
export function enregistrerElement(type, definition) {
  if (elements.has(type) || !['creer', 'boite', 'dessiner'].every(k => typeof definition[k] === 'function')) {
    throw new Error('Type d’élément invalide ou déjà inscrit');
  }
  elements.set(type, definition);
}
for (const [type, definition] of Object.entries({ texte, rectangle, ellipse, ligne })) enregistrerElement(type, definition);
export function typeElement(type) { return elements.get(type); }
export function dessinerElement(ctx, e) { elements.get(e?.type)?.dessiner(ctx, e); }
export function boiteElement(e) { return elements.get(e?.type)?.boite(e) ?? null; }
export function creerElement(type, params) {
  const definition = elements.get(type);
  if (!definition) throw new Error('Type d’élément inconnu');
  return definition.creer(params);
}
export function copierElement(e) { return e == null ? e : JSON.parse(JSON.stringify(e)); }
export function validerElement(e) {
  // Les données sans type des projets du socle restent lisibles, sans rendu.
  if (!e?.type) return copierElement(e);
  if (!elements.has(e.type)) throw new Error('Type d’élément inconnu');
  if (!['texte', 'rectangle', 'ellipse', 'ligne'].includes(e.type)) {
    const definition = elements.get(e.type);
    return copierElement(definition.valider ? definition.valider(e) : e);
  }
  const cles = e.type === 'ligne' ? ['x', 'y', 'x2', 'y2'] : ['x', 'y', 'largeur', 'hauteur'];
  if (!cles.every(k => Number.isFinite(e[k]) && Math.abs(e[k]) <= 1e6)
      || (e.type !== 'ligne' && (e.largeur <= 0 || e.hauteur <= 0))
      || !/^#[0-9a-f]{6}$/i.test(e.couleur)) throw new Error('Élément invalide');
  if (e.type === 'texte') {
    if (typeof e.contenu !== 'string' || !texte.POLICES.includes(e.police)
        || !Number.isFinite(e.taille) || e.taille < 1 || e.taille > 1000
        || typeof e.gras !== 'boolean' || typeof e.italique !== 'boolean'
        || !['left', 'center', 'right'].includes(e.alignement)) throw new Error('Texte invalide');
  } else if (!Number.isFinite(e.epaisseur) || e.epaisseur < 1 || e.epaisseur > 300
      || (e.remplissage != null && !/^#[0-9a-f]{6}$/i.test(e.remplissage))) throw new Error('Forme invalide');
  return copierElement(e);
}

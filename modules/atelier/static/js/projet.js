import { creerRaster, composer } from './document.js';
import { nettoyerCouleurs } from './palette.js';
import { copierElement, validerElement } from './elements/registre.js';

export function chargerImage(source) {
  return new Promise((resolve, reject) => {
    const image = new Image(); image.onload = () => resolve(image);
    image.onerror = () => reject(new Error('Image illisible')); image.src = source;
  });
}

export async function importerImage(fichier, doc, historique, vue) {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(fichier.type)) {
    throw new Error('Formats acceptés : PNG, JPEG, WebP');
  }
  const url = URL.createObjectURL(fichier);
  try {
    const image = await chargerImage(url);
    const calque = creerRaster(image.naturalWidth, image.naturalHeight, fichier.name);
    calque.ctx2d.drawImage(image, 0, 0);
    const premier = doc.vierge;
    doc.transaction(historique, 'Importer une image', () => {
      if (premier) { doc.largeur = calque.canvas.width; doc.hauteur = calque.canvas.height; }
      doc.vierge = false; doc.calques.push(calque); doc.actifId = calque.id;
    });
    if (premier) vue.ajuster();
  } finally { URL.revokeObjectURL(url); }
}

export function serialiser(doc) {
  return { format: 'atelier', version: 1, largeur: doc.largeur, hauteur: doc.hauteur,
    palette: nettoyerCouleurs(doc.palette), recentes: nettoyerCouleurs(doc.recentes, 12),
    calques: doc.calques.map(c => ({ id: c.id, nom: c.nom, type: c.type, visible: c.visible,
      opacite: c.opacite, fusion: c.fusion, x: c.x, y: c.y, sourceId: c.sourceId,
      donnees: c.type === 'raster' ? c.canvas.toDataURL('image/png') : copierElement(c.donnees) })) };
}

function dimension(valeur) { return Number.isInteger(valeur) && valeur > 0 && valeur <= 16384; }
async function lireRaster(source) {
  const image = await chargerImage(source);
  if (!dimension(image.naturalWidth) || !dimension(image.naturalHeight)) throw new Error('Image trop grande');
  const calque = creerRaster(image.naturalWidth, image.naturalHeight);
  calque.ctx2d.drawImage(image, 0, 0); return calque;
}
export async function deserialiser(projet, chargerRaster = lireRaster) {
  if (projet?.format !== 'atelier' || projet.version !== 1 || !dimension(projet.largeur)
      || !dimension(projet.hauteur) || !Array.isArray(projet.calques)) throw new Error('Projet Atelier invalide');
  const calques = [], ids = new Set();
  for (const c of projet.calques) {
    if (!c || !['raster', 'element'].includes(c.type) || typeof c.id !== 'string' || ids.has(c.id)
        || typeof c.nom !== 'string' || typeof c.visible !== 'boolean'
        || !Number.isFinite(c.opacite) || c.opacite < 0 || c.opacite > 1
        || !['source-over', 'multiply'].includes(c.fusion)
        || !Number.isFinite(c.x) || !Number.isFinite(c.y)) throw new Error('Calque invalide');
    ids.add(c.id);
    let calque;
    if (c.type === 'raster') {
      if (typeof c.donnees !== 'string' || !c.donnees.startsWith('data:image/png;base64,')) {
        throw new Error('Données raster invalides');
      }
      calque = await chargerRaster(c.donnees);
    } else calque = { donnees: validerElement(c.donnees) };
    Object.assign(calque, { id: c.id, nom: c.nom, type: c.type, visible: c.visible,
      opacite: c.opacite, fusion: c.fusion, x: c.x, y: c.y });
    if (typeof c.sourceId === 'string') calque.sourceId = c.sourceId;
    calques.push(calque);
  }
  return { largeur: projet.largeur, hauteur: projet.hauteur, calques,
    palette: nettoyerCouleurs(projet.palette), recentes: nettoyerCouleurs(projet.recentes, 12),
    actifId: calques.at(-1)?.id ?? null, vierge: false };
}

async function api(url, options) {
  const reponse = await fetch(url, options);
  if (!reponse.ok) {
    let message = `Erreur serveur (${reponse.status})`;
    try { message = (await reponse.json()).detail || message; } catch { /* Réponse non JSON. */ }
    throw new Error(message);
  }
  return reponse.json();
}

export function installerProjet(ctx, dialogue) {
  let nom = null;
  return {
    reinitialiser() { nom = null; },
    async enregistrer() {
      const choix = nom ?? prompt('Nom du projet (1 à 80 caractères : lettres, chiffres, espaces, - ou _)');
      if (!choix) return;
      if (!/^[\p{L}\p{N}_ -]{1,80}$/u.test(choix) || !choix.trim()) throw new Error('Nom de projet invalide');
      await api(`api/projets/${encodeURIComponent(choix)}`, { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(serialiser(ctx.document)) });
      nom = choix; ctx.message(`Projet « ${nom} » enregistré`);
    },
    async ouvrir() {
      const noms = await api('api/projets');
      const liste = dialogue.querySelector('select'); liste.replaceChildren();
      for (const nom of noms) {
        const option = document.createElement('option'); option.value = nom; option.textContent = nom; liste.append(option);
      }
      dialogue.querySelector('[data-ouvrir]').disabled = noms.length === 0;
      dialogue.querySelector('[data-vide]').hidden = noms.length !== 0;
      const choix = await new Promise(resolve => {
        dialogue.addEventListener('close', () => resolve(dialogue.returnValue === 'ouvrir' ? liste.value : null), { once: true });
        dialogue.returnValue = ''; dialogue.showModal();
      });
      if (!choix) return;
      const etat = await deserialiser(await api(`api/projets/${encodeURIComponent(choix)}`));
      if (!confirm('Remplacer le document actuel par ce projet ?')) return;
      ctx.reinitialiserRetouche?.();
      ctx.document.restaurer(etat); ctx.historique.vider(); ctx.vue.ajuster(); nom = choix;
      ctx.message(`Projet « ${nom} » ouvert`);
    }
  };
}

export function composerPNG(doc) {
  const canvas = document.createElement('canvas'); canvas.width = doc.largeur; canvas.height = doc.hauteur;
  composer(canvas.getContext('2d'), doc);
  return canvas;
}

export async function exporterPNG(doc) {
  const canvas = composerPNG(doc);
  const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
  if (!blob) throw new Error('Export PNG impossible');
  const url = URL.createObjectURL(blob), lien = document.createElement('a');
  lien.href = url; lien.download = 'atelier.png'; lien.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

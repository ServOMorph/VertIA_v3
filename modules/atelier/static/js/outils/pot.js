import { creerRaster } from '../document.js';
import { instantaneRegion } from '../historique.js';
import { pointCalque, imageSource, prelever } from '../echantillon.js';
import { calculer, pendantCalcul } from '../calcul.js';
import { caseOption, nombreOption, sourceOption } from './options.js';

const options = { automatique: true, seuil: 128, rayon: 1, tolerance: 32, source: 'actif', multiplication: true };

export async function appliquerPot(ctx, e) {
  if (e.button !== 0 || ctx.occupe) return;
  if (e.altKey) { prelever(ctx, e, true); return; }
  const doc = ctx.document, actif = ctx.calqueActif;
  if (actif?.type !== 'raster') { ctx.message('Sélectionnez un calque raster'); return; }
  // Un calque Couleurs conserve le lien vers son dessin, y compris après réouverture.
  const source = doc.calques.find(c => c.id === actif.sourceId && c.type === 'raster') ?? actif;
  const point = pointCalque(ctx.vue.coordonnees(e), source);
  if (point.x < 0 || point.y < 0 || point.x >= source.canvas.width || point.y >= source.canvas.height) return;
  const reglages = { ...options }, couleur = [...ctx.couleur];
  await pendantCalcul(ctx, async () => {
    const revision = doc.revision, image = imageSource(doc, source, reglages.source === 'visibles');
    const cle = JSON.stringify([source.id, source.x, source.y, image.width, image.height,
      reglages.source, reglages.automatique, reglages.seuil, reglages.rayon]);
    const resultat = await calculer({ type: 'pot', rgba: image.data, largeur: image.width, hauteur: image.height,
      x: point.x, y: point.y, options: reglages, cle });
    if (doc.revision !== revision) { ctx.message('Document modifié pendant le calcul, recommencez'); return; }
    if (!resultat.boite) { ctx.message('Zone vide : départ sur le trait ou hors de l’image'); return; }
    let cible = actif, nouveau = false;
    if (reglages.multiplication) {
      cible = doc.calques.find(c => c.sourceId === source.id && c.type === 'raster' && c.fusion === 'multiply'
        && c.visible && c.canvas.width === source.canvas.width && c.canvas.height === source.canvas.height
        && c.x === source.x && c.y === source.y && doc.calques.indexOf(c) > doc.calques.indexOf(source));
      if (!cible) {
        cible = creerRaster(source.canvas.width, source.canvas.height, 'Couleurs');
        Object.assign(cible, { fusion: 'multiply', x: source.x, y: source.y, sourceId: source.id }); nouveau = true;
      }
    }
    // Le mode direct utilise les coordonnées du calque actif, qui peut être déplacé indépendamment.
    const dx = source.x - cible.x, dy = source.y - cible.y, b = resultat.boite;
    const x = Math.max(0, Math.floor(b.x + dx)), y = Math.max(0, Math.floor(b.y + dy));
    const droite = Math.min(cible.canvas.width, Math.ceil(b.x + dx + b.largeur));
    const bas = Math.min(cible.canvas.height, Math.ceil(b.y + dy + b.hauteur));
    if (droite <= x || bas <= y) return;
    const capture = instantaneRegion(cible, x, y, droite - x, bas - y);
    const region = cible.ctx2d.getImageData(x, y, droite - x, bas - y);
    const masque = new Uint8Array(region.width * region.height);
    for (let yy = 0; yy < region.height; yy++) for (let xx = 0; xx < region.width; xx++) {
      const sx = Math.floor(x + xx - dx), sy = Math.floor(y + yy - dy);
      if (sx >= 0 && sy >= 0 && sx < image.width && sy < image.height) masque[yy * region.width + xx] = resultat.masque[sy * image.width + sx];
    }
    const peinte = await calculer({ type: 'peindre', rgba: region.data, largeur: region.width, hauteur: region.height,
      masque, options: { couleur, multiplier: !reglages.multiplication } });
    if (doc.revision !== revision) { ctx.message('Document modifié pendant le calcul, recommencez'); return; }
    cible.ctx2d.putImageData(new ImageData(peinte, region.width, region.height), x, y);
    const pixels = capture.terminer('Remplir la zone'), ancienActif = doc.actifId;
    const inserer = () => { doc.calques.splice(doc.calques.indexOf(source) + 1, 0, cible); };
    if (nouveau) inserer();
    doc.actifId = cible.id;
    ctx.historique.enregistrer({ libelle: pixels.libelle,
      annuler() {
        pixels.annuler();
        if (nouveau) doc.calques = doc.calques.filter(c => c !== cible);
        doc.actifId = ancienActif; doc.notifier();
      },
      retablir() { if (nouveau) inserer(); pixels.retablir(); doc.actifId = cible.id; doc.notifier(); }
    });
    doc.notifier(); ctx.memoriserCouleur?.(couleur);
    ctx.message(`Zone remplie · seuil ${resultat.seuil}`);
  });
}

export default {
  id: 'pot', libelle: 'Pot de peinture', raccourci: 'g', curseur: 'crosshair', pointeurBas: appliquerPot,
  panneauOptions() {
    const panneau = document.createElement('div');
    const auto = caseOption(panneau, 'Automatique (Otsu)', options.automatique, valeur => {
      options.automatique = valeur; seuil.disabled = valeur;
    });
    const seuil = nombreOption(panneau, 'Seuil', options.seuil, 0, 255, valeur => { options.seuil = valeur; }); seuil.disabled = auto.checked;
    nombreOption(panneau, 'Fermeture des trous (px)', options.rayon, 0, 3, valeur => { options.rayon = valeur; });
    nombreOption(panneau, 'Tolérance', options.tolerance, 0, 255, valeur => { options.tolerance = valeur; });
    sourceOption(panneau, options.source, valeur => { options.source = valeur; });
    caseOption(panneau, 'Remplir dans un calque de couleur en multiplication', options.multiplication, valeur => { options.multiplication = valeur; });
    const aide = document.createElement('p'); aide.textContent = 'Alt+clic : prélever la couleur visible. Un clic sur le trait ne remplit rien.'; panneau.append(aide);
    return panneau;
  }
};

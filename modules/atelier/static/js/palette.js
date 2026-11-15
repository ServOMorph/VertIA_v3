import { versHex, depuisHex } from './algo/couleur.js';
import { calculer, pendantCalcul } from './calcul.js';
import { caseOption, nombreOption } from './outils/options.js';

export function nettoyerCouleurs(valeur, limite = 24) {
  return Array.isArray(valeur) ? [...new Set(valeur.filter(c => typeof c === 'string' && /^#[0-9a-f]{6}$/i.test(c))
    .map(c => c.toLowerCase()))].slice(0, limite) : [];
}

export function installerPalette(ctx, panneau, couleurInput, alphaInput) {
  const doc = ctx.document, cleStockage = 'atelier.couleurs-recentes';
  try { doc.recentes = nettoyerCouleurs(JSON.parse(localStorage.getItem(cleStockage)), 12); } catch { doc.recentes = []; }
  const titre = document.createElement('h2'); titre.textContent = 'Palette';
  const sourceLabel = document.createElement('label'), source = document.createElement('select');
  sourceLabel.append('Calque de référence ', source);
  const reglages = document.createElement('div'); let n = 8, ignorerPapierTrait = true;
  nombreOption(reglages, 'Nombre de couleurs', n, 2, 24, valeur => { n = valeur; }, 'number');
  caseOption(reglages, 'Ignorer le quasi-blanc et le quasi-noir', true, valeur => { ignorerPapierTrait = valeur; });
  const extraire = document.createElement('button'); extraire.type = 'button'; extraire.textContent = 'Extraire les couleurs';
  const couleurs = document.createElement('div'), recentes = document.createElement('div');
  couleurs.className = recentes.className = 'pastilles';
  const titreRecentes = document.createElement('h3'); titreRecentes.textContent = 'Couleurs récentes';
  panneau.append(titre, sourceLabel, reglages, extraire, couleurs, titreRecentes, recentes);
  const memoriser = () => {
    try { localStorage.setItem(cleStockage, JSON.stringify(doc.recentes)); } catch { /* Le projet conserve les couleurs même sans stockage local. */ }
  };
  const pastilles = (conteneur, liste) => {
    conteneur.replaceChildren();
    for (const hex of liste) {
      const bouton = document.createElement('button'); bouton.type = 'button'; bouton.className = 'pastille';
      bouton.style.backgroundColor = hex; bouton.title = hex; bouton.setAttribute('aria-label', hex);
      bouton.onclick = () => ctx.definirCouleur([...depuisHex(hex), ctx.couleur[3]]); conteneur.append(bouton);
    }
  };
  const rendre = () => {
    const choix = source.value;
    source.replaceChildren();
    for (const calque of doc.calques.filter(c => c.type === 'raster')) {
      const option = document.createElement('option'); option.value = calque.id; option.textContent = calque.nom; source.append(option);
    }
    if ([...source.options].some(o => o.value === choix)) source.value = choix;
    else if ([...source.options].some(o => o.value === doc.actifId)) source.value = doc.actifId;
    extraire.disabled = !source.options.length;
    pastilles(couleurs, doc.palette); pastilles(recentes, doc.recentes); memoriser();
  };
  ctx.memoriserCouleur = couleur => {
    const hex = versHex(couleur); doc.recentes = [hex, ...doc.recentes.filter(c => c !== hex)].slice(0, 12);
    pastilles(recentes, doc.recentes); memoriser();
  };
  ctx.definirCouleur = couleur => {
    ctx.couleur = couleur; couleurInput.value = versHex(couleur); alphaInput.value = Math.round(couleur[3] * 100);
    ctx.memoriserCouleur(couleur);
  };
  extraire.onclick = () => pendantCalcul(ctx, async () => {
    const calque = doc.calques.find(c => c.id === source.value && c.type === 'raster');
    if (!calque) return;
    const revision = doc.revision;
    // Le scan de référence entier est local au calque : son décalage n'affecte pas ses couleurs.
    const rgba = calque.ctx2d.getImageData(0, 0, calque.canvas.width, calque.canvas.height).data;
    const resultat = await calculer({ type: 'palette', rgba, options: { n, ignorerPapierTrait } });
    if (doc.revision !== revision) { ctx.message('Document modifié pendant l’extraction, recommencez'); return; }
    doc.palette = resultat.map(c => versHex([c.r, c.g, c.b])); rendre();
    ctx.message(`${doc.palette.length} couleurs extraites`);
  });
  doc.abonner(rendre); rendre();
}

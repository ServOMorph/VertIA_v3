import { creerRaster } from '../document.js';
import { chargerImage, composerPNG } from '../projet.js';
import { interpolerTampons } from './pinceau.js';
import { nombreOption, caseOption } from './options.js';

export function creerMasque(largeur, hauteur) {
  if (![largeur, hauteur].every(n => Number.isInteger(n) && n > 0 && n <= 16384)) throw new Error('Taille de masque invalide');
  return { largeur, hauteur, pixels: new Uint8Array(largeur * hauteur) };
}

export function peindreMasque(masque, point, taille, gomme = false) {
  const rayon = taille / 2;
  for (let y = Math.max(0, Math.floor(point.y - rayon)); y < Math.min(masque.hauteur, Math.ceil(point.y + rayon)); y++) {
    for (let x = Math.max(0, Math.floor(point.x - rayon)); x < Math.min(masque.largeur, Math.ceil(point.x + rayon)); x++) {
      if (Math.hypot(x + .5 - point.x, y + .5 - point.y) <= rayon) masque.pixels[y * masque.largeur + x] = gomme ? 0 : 255;
    }
  }
}

export function inverserMasque(masque) {
  masque.pixels.forEach((v, i) => { masque.pixels[i] = 255 - v; });
}

export function pixelsMasque(masque, rouge = false) {
  const rgba = new Uint8ClampedArray(masque.pixels.length * 4);
  masque.pixels.forEach((v, i) => {
    rgba.set(rouge ? [255, 0, 0, Math.round(v * .45)] : [v, v, v, 255], i * 4);
  });
  return rgba;
}

export function ajouterRetouche(doc, historique, calque) {
  doc.transaction(historique, 'Retouche IA', () => {
    calque.nom = 'Retouche IA'; doc.calques.push(calque); doc.actifId = calque.id; doc.vierge = false;
  });
}

export function creerSuivi({ fetcher = (...args) => fetch(...args), programmer = setTimeout,
  deprogrammer = clearTimeout, notifier = () => {}, resultat = async () => {} } = {}) {
  let id = null, minuterie = null, controle = null, generation = 0, debut = 0;
  const arreter = () => {
    generation++; deprogrammer(minuterie); minuterie = null; controle?.abort(); controle = null;
  };
  const requete = async (url, options = {}) => {
    const reponse = await fetcher(url, { ...options, signal: controle?.signal });
    if (!reponse.ok) {
      let message = `Erreur serveur (${reponse.status})`;
      try { message = (await reponse.json()).detail || message; } catch { /* Réponse non JSON. */ }
      throw new Error(message);
    }
    return reponse;
  };
  return {
    arreter,
    async lancer(donnees) {
      arreter(); const courant = generation; id = null; debut = Date.now(); controle = new AbortController();
      const publier = etat => notifier({ ...etat, secondes: Math.floor((Date.now() - debut) / 1000) });
      const interroger = async () => {
        minuterie = null;
        try {
          const etat = await (await requete(`/api/retouche/${id}`)).json();
          if (courant !== generation) return;
          if (etat.etat === 'termine') {
            const reponse = await requete(`/api/retouche/${id}/resultat`);
            const blob = await reponse.blob();
            if (courant !== generation) return;
            await resultat(blob, () => courant === generation);
            if (courant !== generation) return;
          }
          publier(etat);
          if (['attente', 'en_cours'].includes(etat.etat)) minuterie = programmer(interroger, 3000);
        } catch (erreur) {
          if (courant === generation) publier({ etat: 'echec', message: erreur.message });
        }
      };
      try {
        publier({ etat: 'attente', message: 'En attente' });
        const reponse = await (await requete('/api/retouche', { method: 'POST',
          headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(donnees) })).json();
        if (courant !== generation) return;
        id = reponse.id; await interroger();
      } catch (erreur) {
        if (courant === generation) publier({ etat: 'echec', message: erreur.message });
      }
    },
    async annuler() {
      if (!id) throw new Error('Attendez la prise en charge de la retouche');
      await requete(`/api/retouche/${id}`, { method: 'DELETE' });
      arreter(); notifier({ etat: 'annule', message: 'Annulé', secondes: 0 });
    }
  };
}

export function creerRetouche() {
  let masque = null, apercu = null, sale = true, precedent = null, suivi = null;
  let taille = 40, gomme = false, prompt = '', force = .85, actif = false, etat = 'Prêt';
  let sortie = null, lancer = null, annuler = null;
  const assurer = ctx => {
    const doc = ctx.document;
    if (masque?.largeur !== doc.largeur || masque?.hauteur !== doc.hauteur) {
      masque = creerMasque(doc.largeur, doc.hauteur);
      apercu = document.createElement('canvas'); apercu.width = doc.largeur; apercu.height = doc.hauteur; sale = true;
    }
  };
  const rafraichir = ctx => { sale = true; ctx.vue.invalider(); };
  const afficher = () => {
    if (sortie) sortie.textContent = etat;
    if (lancer) lancer.disabled = actif;
    if (annuler) annuler.disabled = !actif;
  };
  const configurer = ctx => {
    if (suivi) return;
    suivi = creerSuivi({ notifier(e) {
      actif = ['attente', 'en_cours'].includes(e.etat);
      ctx.verrouillerRetouche?.(actif);
      etat = `${e.message}${actif ? ` · ${e.secondes} s` : ''}`; afficher(); ctx.message(etat);
    }, async resultat(blob, estActuel) {
      const url = URL.createObjectURL(blob);
      try {
        const image = await chargerImage(url), doc = ctx.document;
        if (!estActuel()) return;
        const calque = creerRaster(doc.largeur, doc.hauteur, 'Retouche IA');
        calque.ctx2d.drawImage(image, 0, 0, doc.largeur, doc.hauteur);
        ajouterRetouche(doc, ctx.historique, calque);
        masque.pixels.fill(0); rafraichir(ctx);
      } finally { URL.revokeObjectURL(url); }
    } });
    globalThis.addEventListener?.('pagehide', () => { suivi.arreter(); actif = false; ctx.verrouillerRetouche?.(false); });
  };
  const canvasMasque = () => {
    const canvas = document.createElement('canvas'); canvas.width = masque.largeur; canvas.height = masque.hauteur;
    const rendu = canvas.getContext('2d'), image = rendu.createImageData(canvas.width, canvas.height);
    image.data.set(pixelsMasque(masque)); rendu.putImageData(image, 0, 0); return canvas;
  };
  return {
    id: 'retouche', libelle: 'Retouche IA', curseur: 'crosshair',
    reinitialiser() { masque = null; apercu = null; precedent = null; sale = true; },
    activer(ctx) { assurer(ctx); configurer(ctx); },
    desactiver() { precedent = null; },
    panneauOptions(ctx) {
      assurer(ctx); configurer(ctx);
      const panneau = document.createElement('div');
      nombreOption(panneau, 'Taille du masque (px)', taille, 1, 300, v => { taille = v; });
      caseOption(panneau, 'Gomme du masque', gomme, v => { gomme = v; });
      const bouton = (texte, action) => {
        const b = document.createElement('button'); b.type = 'button'; b.textContent = texte; b.onclick = action; panneau.append(b); return b;
      };
      bouton('Effacer le masque', () => { if (!actif) { masque.pixels.fill(0); rafraichir(ctx); } });
      bouton('Inverser', () => { if (!actif) { inverserMasque(masque); rafraichir(ctx); } });
      const label = document.createElement('label'), texte = document.createElement('textarea');
      label.append('Décrire la retouche', texte); texte.maxLength = 4000; texte.value = prompt;
      texte.oninput = () => { prompt = texte.value; }; panneau.append(label);
      const curseur = nombreOption(panneau, 'Force', force, .3, 1, v => { force = v; });
      curseur.step = .01; curseur.value = force;
      lancer = bouton('Lancer', async () => {
        if (actif) return;
        try {
          assurer(ctx);
          if (!masque.pixels.some(v => v > 0)) throw new Error('Peignez une zone du masque avant de lancer');
          if (!prompt.trim()) throw new Error('Décrivez la retouche');
          const donnees = { image: composerPNG(ctx.document).toDataURL('image/png'),
            masque: canvasMasque().toDataURL('image/png'), prompt, force, etapes: 20, seed: -1 };
          await suivi.lancer(donnees);
        } catch (erreur) { etat = erreur.message; afficher(); ctx.message(etat); }
      });
      annuler = bouton('Annuler la retouche', async () => {
        try { await suivi.annuler(); } catch (erreur) { ctx.message(erreur.message); }
      });
      sortie = document.createElement('p'); sortie.setAttribute('role', 'status'); sortie.setAttribute('aria-live', 'polite');
      panneau.append(sortie); afficher(); return panneau;
    },
    dessinerSurimpression(ctx, rendu) {
      assurer(ctx);
      if (sale) {
        const r = apercu.getContext('2d'), image = r.createImageData(masque.largeur, masque.hauteur);
        image.data.set(pixelsMasque(masque, true)); r.putImageData(image, 0, 0); sale = false;
      }
      rendu.drawImage(apercu, 0, 0);
    },
    pointeurBas(ctx, e) {
      if (e.button !== 0 || actif) return;
      assurer(ctx); precedent = ctx.vue.coordonnees(e); peindreMasque(masque, precedent, taille, gomme); rafraichir(ctx);
    },
    pointeurDeplace(ctx, e) {
      if (!precedent || actif) return;
      const point = ctx.vue.coordonnees(e);
      for (const p of interpolerTampons(precedent, point, taille)) peindreMasque(masque, p, taille, gomme);
      precedent = point; rafraichir(ctx);
    },
    pointeurHaut(ctx, e) { if (e.type === 'pointerup') this.pointeurDeplace(ctx, e); precedent = null; }
  };
}

export default creerRetouche();

import { masqueTrait, histogramme, otsu } from './algo/seuil.js';
import { dilater } from './algo/morpho.js';
import { remplir } from './algo/remplissage.js';
import { extraireCouleurs } from './algo/kmeans.js';
import { peindre } from './algo/couleur.js';

let cache = null;
function memesPixels(a, b) {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}
self.onmessage = ({ data: requete }) => {
  const { id, type, rgba, largeur, hauteur, options } = requete;
  try {
    if (type === 'peindre') {
      const resultat = peindre(rgba, largeur, requete.masque,
        { x: 0, y: 0, largeur, hauteur }, options.couleur, options.multiplier);
      self.postMessage({ id, resultat }, [resultat.buffer]); return;
    }
    if (type === 'palette') {
      self.postMessage({ id, resultat: extraireCouleurs(rgba, options.n, options) }); return;
    }
    const cacheUtilise = cache?.cle === requete.cle && memesPixels(cache.rgba, rgba);
    if (!cacheUtilise) {
      const seuil = options.automatique ? otsu(histogramme(rgba)) : options.seuil;
      cache = { cle: requete.cle, rgba, trait: dilater(masqueTrait(rgba, largeur, hauteur, seuil), largeur, hauteur, options.rayon), seuil };
    }
    const resultat = remplir(cache.rgba, largeur, hauteur, cache.trait, requete.x, requete.y, options);
    resultat.seuil = cache.seuil; resultat.cacheUtilise = cacheUtilise;
    self.postMessage({ id, resultat }, [resultat.masque.buffer]);
  } catch (erreur) { self.postMessage({ id, erreur: erreur.message }); }
};

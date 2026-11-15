import { instantaneRegion } from '../historique.js';
import { nombreOption } from './options.js';

export function interpolerTampons(a, b, taille) {
  const distance = Math.hypot(b.x - a.x, b.y - a.y), pas = Math.max(0.25, taille / 4);
  const n = Math.max(1, Math.ceil(distance / pas));
  return Array.from({ length: n }, (_, i) => ({ x: a.x + (b.x - a.x) * (i + 1) / n, y: a.y + (b.y - a.y) * (i + 1) / n }));
}
function canvas(largeur, hauteur) {
  const c = document.createElement('canvas'); c.width = largeur; c.height = hauteur; return c;
}
export function creerPinceau(gomme = false) {
  const options = { taille: 30, durete: 80, opacite: 100 };
  let geste = null, curseur = null;
  const local = (ctx, e, calque) => {
    const p = ctx.vue.coordonnees(e); return { x: p.x - calque.x, y: p.y - calque.y };
  };
  const tamponner = p => {
    const g = geste, r = g.taille / 2, m = g.masque.getContext('2d');
    m.drawImage(g.tampon, p.x - r, p.y - r, g.taille, g.taille);
    g.gauche = Math.min(g.gauche, Math.floor(p.x - r - 1)); g.haut = Math.min(g.haut, Math.floor(p.y - r - 1));
    g.droite = Math.max(g.droite, Math.ceil(p.x + r + 1)); g.bas = Math.max(g.bas, Math.ceil(p.y + r + 1));
  };
  const composerTrait = (rendu, g) => {
    rendu.save(); rendu.globalAlpha = g.alpha;
    rendu.globalCompositeOperation = gomme ? 'destination-out' : 'source-over';
    rendu.drawImage(g.masque, 0, 0); rendu.restore();
  };
  const apercu = ctx => {
    const g = geste, rendu = g.calque.apercuCanvas.getContext('2d');
    rendu.clearRect(0, 0, g.masque.width, g.masque.height); rendu.drawImage(g.calque.canvas, 0, 0);
    composerTrait(rendu, g); ctx.vue.invalider();
  };
  const terminer = (ctx, annuler) => {
    if (!geste) return;
    const g = geste; geste = null; delete g.calque.apercuCanvas;
    const x = Math.max(0, g.gauche), y = Math.max(0, g.haut);
    const droite = Math.min(g.calque.canvas.width, g.droite), bas = Math.min(g.calque.canvas.height, g.bas);
    if (!annuler && droite > x && bas > y) {
      const capture = instantaneRegion(g.calque, x, y, droite - x, bas - y);
      composerTrait(g.calque.ctx2d, g);
      ctx.historique.enregistrer(capture.terminer(gomme ? 'Gommer le trait' : 'Peindre le trait'));
      ctx.notifier(); if (!gomme) ctx.memoriserCouleur?.(g.couleur);
    }
    ctx.vue.invalider();
  };
  return {
    id: gomme ? 'gomme' : 'pinceau', libelle: gomme ? 'Gomme' : 'Pinceau', raccourci: gomme ? 'e' : 'b', curseur: 'crosshair',
    desactiver(ctx) { terminer(ctx, true); curseur = null; },
    panneauOptions() {
      const panneau = document.createElement('div');
      for (const [cle, texte, min, max] of [['taille', 'Taille (px)', 1, 300], ['durete', 'Dureté (%)', 0, 100], ['opacite', 'Opacité (%)', 1, 100]]) {
        nombreOption(panneau, texte, options[cle], min, max, v => { options[cle] = v; });
      }
      return panneau;
    },
    survol(ctx, e) { curseur = e ? ctx.vue.coordonnees(e) : null; ctx.vue.invalider(); },
    dessinerSurimpression(ctx, rendu) {
      if (!curseur) return;
      rendu.beginPath(); rendu.arc(curseur.x, curseur.y, (geste?.taille ?? options.taille) / 2, 0, Math.PI * 2);
      rendu.lineWidth = 3 / ctx.vue.zoom; rendu.strokeStyle = '#fff'; rendu.stroke();
      rendu.lineWidth = 1 / ctx.vue.zoom; rendu.strokeStyle = '#202934'; rendu.stroke();
    },
    pointeurBas(ctx, e) {
      if (e.button !== 0 || ctx.occupe) return;
      const calque = ctx.calqueActif;
      if (calque?.type !== 'raster') { ctx.message('Sélectionnez un calque raster'); return; }
      const taille = options.taille, tampon = canvas(Math.ceil(taille), Math.ceil(taille));
      const t = tampon.getContext('2d'), r = tampon.width / 2, couleur = [...ctx.couleur];
      const rgb = gomme ? '0,0,0' : couleur.slice(0, 3).join(',');
      const gradient = t.createRadialGradient(r, r, r * Math.min(0.999, options.durete / 100), r, r, r);
      gradient.addColorStop(0, `rgba(${rgb},1)`); gradient.addColorStop(1, `rgba(${rgb},0)`);
      t.fillStyle = options.durete === 100 ? `rgb(${rgb})` : gradient;
      t.beginPath(); t.arc(r, r, r, 0, Math.PI * 2); t.fill();
      geste = { calque, taille, tampon, couleur, alpha: options.opacite / 100 * (gomme ? 1 : couleur[3]),
        masque: canvas(calque.canvas.width, calque.canvas.height), gauche: Infinity, haut: Infinity, droite: -Infinity, bas: -Infinity };
      calque.apercuCanvas = canvas(calque.canvas.width, calque.canvas.height);
      geste.precedent = local(ctx, e, calque); tamponner(geste.precedent); apercu(ctx);
    },
    pointeurDeplace(ctx, e) {
      if (!geste) return;
      const p = local(ctx, e, geste.calque);
      for (const point of interpolerTampons(geste.precedent, p, geste.taille)) tamponner(point);
      geste.precedent = p; apercu(ctx);
    },
    pointeurHaut(ctx, e) {
      if (geste && e.type === 'pointerup') this.pointeurDeplace(ctx, e);
      terminer(ctx, e.type !== 'pointerup');
    }
  };
}
export default creerPinceau();

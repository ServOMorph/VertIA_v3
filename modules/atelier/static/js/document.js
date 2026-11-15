import { dessinerElement } from './elements/registre.js';

const rendus = new Map();
export function enregistrerRendu(type, rendu) { rendus.set(type, rendu); }
enregistrerRendu('raster', (ctx, calque) => ctx.drawImage(calque.apercuCanvas ?? calque.canvas, 0, 0));
enregistrerRendu('element', (ctx, calque) => dessinerElement(ctx, calque.donnees));

export function creerCalqueElement(donnees, nom = 'Élément') {
  return { id: crypto.randomUUID(), nom, type: 'element', visible: true,
    opacite: 1, fusion: 'source-over', x: 0, y: 0, donnees };
}

export function creerRaster(largeur, hauteur, nom = 'Calque') {
  const canvas = document.createElement('canvas');
  canvas.width = largeur; canvas.height = hauteur;
  return { id: crypto.randomUUID(), nom, type: 'raster', visible: true,
    opacite: 1, fusion: 'source-over', x: 0, y: 0, canvas,
    ctx2d: canvas.getContext('2d', { willReadFrequently: true }) };
}

export function composer(ctx, doc) {
  for (const calque of doc.calques) {
    if (!calque.visible) continue;
    ctx.save();
    ctx.globalAlpha = calque.opacite;
    ctx.globalCompositeOperation = calque.fusion;
    ctx.translate(calque.x, calque.y);
    rendus.get(calque.type)?.(ctx, calque);
    ctx.restore();
  }
}

export class DocumentAtelier {
  constructor() {
    this.largeur = 1200; this.hauteur = 800;
    this.calques = []; this.actifId = null; this.vierge = true;
    this.abonnes = new Set(); this.revision = 0; this.palette = []; this.recentes = [];
  }
  get calqueActif() { return this.calques.find(c => c.id === this.actifId) ?? null; }
  abonner(fn) { this.abonnes.add(fn); }
  notifier() { this.revision++; for (const fn of this.abonnes) fn(); }
  etat() {
    return { largeur: this.largeur, hauteur: this.hauteur, calques: [...this.calques],
      actifId: this.actifId, vierge: this.vierge, palette: [...this.palette], recentes: [...this.recentes] };
  }
  restaurer(etat) { Object.assign(this, etat, { calques: [...etat.calques] }); this.notifier(); }
  transaction(historique, libelle, operation) {
    const avant = this.etat(); operation(); const apres = this.etat();
    historique.enregistrer({ libelle, annuler: () => this.restaurer(avant),
      retablir: () => this.restaurer(apres) });
    this.notifier();
  }
  modifier(historique, calque, changements, libelle) {
    const avant = Object.fromEntries(Object.keys(changements).map(k => [k, calque[k]]));
    const appliquer = valeurs => { Object.assign(calque, valeurs); this.notifier(); };
    appliquer(changements);
    historique.enregistrer({ libelle, annuler: () => appliquer(avant), retablir: () => appliquer(changements) });
  }
}

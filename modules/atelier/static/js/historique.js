export const MAX_PAS = 40;

export class Historique {
  constructor(notifier = () => {}) { this.passes = []; this.futurs = []; this.notifier = notifier; }
  enregistrer(action) {
    this.passes.push(action);
    if (this.passes.length > MAX_PAS) this.passes.shift();
    this.futurs = []; this.notifier();
  }
  annuler() {
    const action = this.passes.pop();
    if (action) { action.annuler(); this.futurs.push(action); this.notifier(); }
  }
  retablir() {
    const action = this.futurs.pop();
    if (action) { action.retablir(); this.passes.push(action); this.notifier(); }
  }
  vider() { this.passes = []; this.futurs = []; this.notifier(); }
}

// Capturer avant le geste, puis appeler terminer() après les modifications.
// L'action retournée ne conserve que le rectangle concerné, en coordonnées du calque.
export function instantaneRegion(calque, x, y, l, h) {
  const gauche = Math.max(0, Math.floor(x)), haut = Math.max(0, Math.floor(y));
  const droite = Math.min(calque.canvas.width, Math.ceil(x + l));
  const bas = Math.min(calque.canvas.height, Math.ceil(y + h));
  if (droite <= gauche || bas <= haut) throw new Error('Zone de pixels vide');
  const avant = calque.ctx2d.getImageData(gauche, haut, droite - gauche, bas - haut);
  return { terminer(libelle = 'Modifier les pixels') {
    const apres = calque.ctx2d.getImageData(gauche, haut, droite - gauche, bas - haut);
    return { libelle,
      annuler: () => calque.ctx2d.putImageData(avant, gauche, haut),
      retablir: () => calque.ctx2d.putImageData(apres, gauche, haut) };
  } };
}

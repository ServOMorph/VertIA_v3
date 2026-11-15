import { composer } from './document.js';

export class Vue {
  constructor(doc, zone, canvas, statut) {
    this.document = doc; this.zone = zone; this.canvas = canvas; this.statut = statut;
    this.zoom = 1; this.attente = false;
    doc.abonner(() => this.invalider());
    new ResizeObserver(() => this.invalider()).observe(zone);
    zone.addEventListener('wheel', e => {
      if (e.ctrlKey || !e.shiftKey) {
        e.preventDefault(); this.zoomer(this.zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15), e);
      }
    }, { passive: false });
  }
  coordonnees(e) {
    const rect = this.canvas.getBoundingClientRect();
    return { x: (e.clientX - rect.left) / this.zoom, y: (e.clientY - rect.top) / this.zoom };
  }
  zoomer(zoom, evenement = null) {
    const rect = this.zone.getBoundingClientRect();
    const px = evenement ? evenement.clientX - rect.left : this.zone.clientWidth / 2;
    const py = evenement ? evenement.clientY - rect.top : this.zone.clientHeight / 2;
    const point = evenement ? this.coordonnees(evenement) : this.coordonnees({
      clientX: rect.left + px, clientY: rect.top + py });
    this.zoom = Math.max(0.02, Math.min(8, zoom));
    this.dimensionner();
    const apres = this.canvas.getBoundingClientRect();
    this.zone.scrollLeft += apres.left - rect.left + point.x * this.zoom - px;
    this.zone.scrollTop += apres.top - rect.top + point.y * this.zoom - py;
    this.invalider();
  }
  ajuster() {
    this.zoom = Math.max(0.02, Math.min(1,
      (this.zone.clientWidth - 64) / this.document.largeur,
      (this.zone.clientHeight - 64) / this.document.hauteur));
    this.dimensionner(); this.zone.scrollLeft = 0; this.zone.scrollTop = 0; this.invalider();
  }
  dimensionner() {
    const largeur = Math.max(1, Math.round(this.document.largeur * this.zoom));
    const hauteur = Math.max(1, Math.round(this.document.hauteur * this.zoom));
    if (this.canvas.width !== largeur) this.canvas.width = largeur;
    if (this.canvas.height !== hauteur) this.canvas.height = hauteur;
    this.canvas.style.width = `${largeur}px`; this.canvas.style.height = `${hauteur}px`;
  }
  invalider() {
    if (this.attente) return;
    this.attente = true;
    requestAnimationFrame(() => { this.attente = false; this.rendre(); });
  }
  rendre() {
    this.dimensionner();
    const ctx = this.canvas.getContext('2d');
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.save(); ctx.scale(this.zoom, this.zoom); composer(ctx, this.document);
    this.surimpression?.(ctx); ctx.restore();
    this.statut.textContent = `${Math.round(this.zoom * 100)} % · ${this.document.largeur} × ${this.document.hauteur} px`;
  }
}

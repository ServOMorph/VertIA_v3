import { composer } from './document.js';

export function pointCalque(point, calque) {
  return { x: Math.floor(point.x - calque.x), y: Math.floor(point.y - calque.y) };
}

export function imageSource(doc, calque, visibles = false) {
  if (!visibles) return calque.ctx2d.getImageData(0, 0, calque.canvas.width, calque.canvas.height);
  const canvas = document.createElement('canvas');
  canvas.width = calque.canvas.width; canvas.height = calque.canvas.height;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.translate(-calque.x, -calque.y); composer(ctx, doc);
  return ctx.getImageData(0, 0, canvas.width, canvas.height);
}

export function prelever(ctx, evenement, visibles = true) {
  const point = ctx.vue.coordonnees(evenement), calque = ctx.calqueActif;
  let pixel;
  if (visibles) {
    const x = Math.floor(point.x), y = Math.floor(point.y);
    if (x < 0 || y < 0 || x >= ctx.document.largeur || y >= ctx.document.hauteur) return;
    const canvas = document.createElement('canvas'); canvas.width = 1; canvas.height = 1;
    const rendu = canvas.getContext('2d'); rendu.translate(-x, -y); composer(rendu, ctx.document);
    pixel = rendu.getImageData(0, 0, 1, 1).data;
  } else {
    if (calque?.type !== 'raster') return;
    const { x, y } = pointCalque(point, calque);
    if (x < 0 || y < 0 || x >= calque.canvas.width || y >= calque.canvas.height) return;
    pixel = calque.ctx2d.getImageData(x, y, 1, 1).data;
  }
  if (pixel[3]) ctx.definirCouleur([...pixel.slice(0, 3), pixel[3] / 255]);
}

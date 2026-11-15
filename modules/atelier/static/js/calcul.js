let worker = null, sequence = 0;
const attentes = new Map();
export function calculer(requete) {
  if (!worker) {
    worker = new Worker(new URL('./calcul-worker.js', import.meta.url), { type: 'module' });
    worker.onmessage = ({ data }) => {
      const attente = attentes.get(data.id); if (!attente) return;
      attentes.delete(data.id);
      if (data.erreur) attente.reject(new Error(data.erreur)); else attente.resolve(data.resultat);
    };
    worker.onerror = () => {
      for (const attente of attentes.values()) attente.reject(new Error('Calcul indisponible : échec du Worker local'));
      attentes.clear(); worker.terminate(); worker = null;
    };
  }
  return new Promise((resolve, reject) => {
    const id = ++sequence; attentes.set(id, { resolve, reject });
    const transferts = [requete.rgba.buffer];
    if (requete.masque) transferts.push(requete.masque.buffer);
    try { worker.postMessage({ ...requete, id }, transferts); }
    catch (erreur) { attentes.delete(id); reject(erreur); }
  });
}

export async function pendantCalcul(ctx, action) {
  if (ctx.occupe) return;
  ctx.occupe = true;
  const principal = document.querySelector('main'), precedent = ctx.vue.zone.style.cursor;
  principal.inert = true; ctx.vue.zone.style.cursor = 'wait'; document.body.style.cursor = 'wait';
  try { return await action(); }
  catch (erreur) { ctx.message(erreur.message); }
  finally {
    ctx.occupe = false; principal.inert = false;
    ctx.vue.zone.style.cursor = precedent; document.body.style.cursor = '';
  }
}

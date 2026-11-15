/** Un outil exporte { id, libelle, raccourci?, curseur?, activer(ctx)?, desactiver(ctx)?,
 * pointeurBas(ctx,e)?, pointeurDeplace(ctx,e)?, pointeurHaut(ctx,e)?, panneauOptions(ctx)? }.
 * panneauOptions retourne HTMLElement ou null. ctx fournit document, calqueActif (getter),
 * vue.coordonnees(e), historique, couleur [r,g,b,a] (0..255, alpha 0..1), notifier().
 * Les pixels natifs sont accessibles par calque.canvas / calque.ctx2d ; les gestes
 * enregistrent une action dans historique et appellent ctx.notifier() après modification.
 */
const outils = new Map();
export function enregistrerOutil(outil) {
  if (!outil.id || !outil.libelle || outils.has(outil.id)) throw new Error('Outil invalide ou déjà inscrit');
  outils.set(outil.id, outil);
}
export function listerOutils() { return [...outils.values()]; }

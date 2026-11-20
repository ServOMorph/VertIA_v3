import { creerRaster } from '../document.js';
import { chargerImage, composerPNG } from '../projet.js';
import { creerSuivi } from './retouche.js';

const QUESTION = 'Que proposes-tu pour améliorer cette image ?';
const MINIMUM = 8;
const borner = (n, min, max) => Math.max(min, Math.min(max, n));
const COINS = [[0, 1], [2, 1], [2, 3], [0, 3]];

export function zoneAvecMarge([x1, y1, x2, y2], largeur, hauteur, marge = .25) {
  const dx = (x2 - x1) * marge, dy = (y2 - y1) * marge;
  return [Math.max(0, Math.floor(x1 - dx)), Math.max(0, Math.floor(y1 - dy)),
    Math.min(largeur, Math.ceil(x2 + dx)), Math.min(hauteur, Math.ceil(y2 + dy))];
}

export function bornerZone(zone, largeur, hauteur, minimum = MINIMUM) {
  if (!Array.isArray(zone) || zone.length !== 4 || !zone.every(Number.isFinite)) return null;
  const [x1, y1, x2, y2] = zone;
  const axe = (a, b, taille) => {
    const min = Math.min(minimum, taille);
    const debut = borner(Math.round(Math.min(a, b)), 0, taille - min);
    return [debut, borner(Math.round(Math.max(a, b)), debut + min, taille)];
  };
  const [gauche, droite] = axe(x1, x2, largeur), [haut, bas] = axe(y1, y2, hauteur);
  return [gauche, haut, droite, bas];
}

export function deplacerZone([x1, y1, x2, y2], dx, dy, largeur, hauteur) {
  dx = borner(Math.round(dx), -x1, largeur - x2);
  dy = borner(Math.round(dy), -y1, hauteur - y2);
  return [x1 + dx, y1 + dy, x2 + dx, y2 + dy];
}

export function redimensionnerZone(zone, coin, point) {
  const [x, y] = COINS[coin], nouvelle = [...zone];
  nouvelle[x] = point.x;
  nouvelle[y] = point.y;
  return nouvelle;
}

export function poignee(zone, point, tolerance) {
  let coin = -1, distance = tolerance;
  COINS.forEach(([x, y], i) => {
    const d = Math.hypot(point.x - zone[x], point.y - zone[y]);
    if (d <= distance) { coin = i; distance = d; }
  });
  return coin;
}

export function ajouterHistorique(historique, question, reponse, max = 20) {
  const titres = reponse.propositions.map(p => `\n- ${p.titre}`);
  const suffixe = Array.from(titres.join('')).slice(0, 8000);
  const texte = Array.from(reponse.reponse).slice(0, 8000 - suffixe.length).join('');
  return max > 0 ? [...historique, { role: 'user', contenu: question },
    { role: 'assistant', contenu: texte + suffixe.join('') }].slice(-max) : [];
}

export function zoneDessin([x1, y1, x2, y2], { x, y, largeur, hauteur }) {
  const marge = Math.ceil(3 * Math.max(2, .004 * Math.max(largeur, hauteur))) + 1;
  return [Math.max(x, x1 - marge), Math.max(y, y1 - marge),
    Math.min(x + largeur, x2 + marge), Math.min(y + hauteur, y2 + marge)];
}

function canvas(largeur, hauteur) {
  const element = document.createElement('canvas');
  element.width = largeur; element.height = hauteur;
  return element;
}

function preparerRetouche(doc, { zone, prompt }) {
  const [x, y, droite, bas] = zoneAvecMarge(zone, doc.largeur, doc.hauteur);
  const largeur = droite - x, hauteur = bas - y;
  const image = canvas(largeur, hauteur), masque = canvas(largeur, hauteur);
  image.getContext('2d').drawImage(composerPNG(doc), x, y, largeur, hauteur, 0, 0, largeur, hauteur);
  const rendu = masque.getContext('2d');
  rendu.fillStyle = '#000'; rendu.fillRect(0, 0, largeur, hauteur);
  rendu.fillStyle = '#fff'; rendu.fillRect(zone[0] - x, zone[1] - y, zone[2] - zone[0], zone[3] - zone[1]);
  return { x, y, largeur, hauteur, donnees: { image: image.toDataURL('image/png'),
    masque: masque.toDataURL('image/png'), prompt, force: .85, etapes: 20, seed: -1 } };
}

function suivre(donnees, options, publier) {
  let terminer, prisEnCharge, termine = false;
  const fin = new Promise(resolve => { terminer = resolve; });
  const priseEnCharge = new Promise(resolve => { prisEnCharge = resolve; });
  const notifier = etat => {
    publier(etat);
    if (!['attente', 'en_cours'].includes(etat.etat)) {
      termine = true;
      terminer(etat);
    }
  };
  const suivi = creerSuivi({ ...options, notifier, fetcher(url, requete) {
    if (!requete.method) prisEnCharge();
    return fetch(url, requete);
  } });
  const lancement = suivi.lancer(donnees);
  return {
    fin,
    async annuler() {
      await Promise.race([priseEnCharge, lancement]);
      if (termine) return;
      try { await suivi.annuler(); }
      catch (erreur) {
        suivi.arreter();
        notifier({ etat: 'echec', message: erreur.message });
        throw erreur;
      }
    }
  };
}

const couleur = index => `hsl(${(215 + index * 137.5) % 360} 75% 44%)`;

export function creerDialogue() {
  let historique = [], propositions = [], question = QUESTION, selection = -1;
  let geste = null, operation = null, dimensions = null, panneau = null, etat = 'Prêt';
  const reinitialiser = () => {
    historique = []; propositions = []; question = QUESTION; selection = -1;
    geste = null; dimensions = null; etat = 'Prêt';
  };
  const verifierDimensions = ({ document: doc }) => {
    if (dimensions && (dimensions[0] !== doc.largeur || dimensions[1] !== doc.hauteur)) reinitialiser();
  };
  const afficher = () => {
    if (!panneau) return;
    panneau.sortie.textContent = etat;
    panneau.saisie.disabled = panneau.envoyer.disabled = Boolean(operation);
    panneau.appliquer.disabled = Boolean(operation) || !propositions.some(p => p.cochee && p.zone);
    panneau.annuler.disabled = !operation || Boolean(operation.annulation);
    panneau.lignes.forEach(({ bouton, texte, caseZone, aide }, i) => {
      const p = propositions[i];
      if (!p) return;
      bouton.setAttribute('aria-pressed', String(i === selection));
      texte.disabled = caseZone.disabled = bouton.disabled = Boolean(operation);
      caseZone.checked = p.cochee;
      aide.hidden = Boolean(p.zone);
    });
  };
  const message = (ctx, texte) => { etat = texte; afficher(); ctx.message(texte); };
  const choisir = (ctx, i) => { selection = i; afficher(); ctx.vue.invalider(); };
  const annulerOperation = ctx => {
    const op = operation;
    if (!op?.suivi || op.annulation) return;
    op.annulation = op.suivi.annuler().catch(erreur => { op.erreurAnnulation = erreur; });
    message(ctx, 'Annulation en cours');
    return op.annulation;
  };
  const lancer = async (ctx, action) => {
    if (operation || geste) return;
    const op = { suivi: null, annulation: null, erreurAnnulation: null };
    operation = op;
    ctx.verrouillerRetouche(true);
    afficher();
    try {
      await action(op);
      if (op.annulation) {
        await op.annulation;
        if (op.erreurAnnulation) throw op.erreurAnnulation;
        message(ctx, 'Annulé');
      }
    } catch (erreur) { message(ctx, erreur.message); }
    finally { operation = null; ctx.verrouillerRetouche(false); afficher(); }
  };
  const executer = async (ctx, op, donnees, options, prefixe) => {
    op.suivi = suivre(donnees, options, e => {
      if (!op.annulation && ['attente', 'en_cours'].includes(e.etat)) {
        message(ctx, `${prefixe}${e.message} · ${e.secondes} s`);
      }
    });
    const resultat = await op.suivi.fin;
    op.suivi = null;
    if (!op.annulation && resultat.etat !== 'termine') throw new Error(`${prefixe}${resultat.message}`);
  };
  const envoyer = ctx => lancer(ctx, async op => {
    verifierDimensions(ctx);
    const texte = question.trim(), doc = ctx.document;
    if (!texte || texte.length > 4000) throw new Error('Saisissez une question de 1 à 4000 caractères');
    const largeur = doc.largeur, hauteur = doc.hauteur;
    let reponse;
    await executer(ctx, op, { image: composerPNG(doc).toDataURL('image/png'), prompt: texte, historique },
      { base: 'api/analyse', typeResultat: 'json', resultat: contenu => { reponse = contenu; } }, '');
    if (op.annulation) return;
    if (typeof reponse?.reponse !== 'string' || !Array.isArray(reponse.propositions)
        || reponse.propositions.some(p => typeof p?.titre !== 'string' || typeof p.prompt !== 'string')) {
      throw new Error('Réponse d’analyse invalide');
    }
    if (doc.largeur !== largeur || doc.hauteur !== hauteur) throw new Error('Les dimensions du document ont changé');
    dimensions = [largeur, hauteur];
    historique = ajouterHistorique(historique, texte, reponse);
    propositions = reponse.propositions.map(p => {
      const zone = bornerZone(p.zone, largeur, hauteur);
      return { titre: p.titre, prompt: p.prompt.slice(0, 4000), zone, cochee: Boolean(zone) };
    });
    selection = propositions.length ? 0 : -1;
    question = '';
    ctx.actualiserOptions();
    ctx.vue.invalider();
    message(ctx, 'Analyse terminée');
  });
  const appliquer = ctx => lancer(ctx, async op => {
    verifierDimensions(ctx);
    const doc = ctx.document, zones = propositions.filter(p => p.cochee && p.zone);
    if (!zones.length) throw new Error('Cochez une proposition avec une zone');
    for (const p of zones) {
      if (!p.prompt.trim() || p.prompt.length > 4000) throw new Error(`${p.titre} · Décrivez la retouche (1 à 4000 caractères)`);
      const { x, y, largeur, hauteur, donnees } = preparerRetouche(doc, p);
      await executer(ctx, op, donnees, { async resultat(blob, estActuel) {
        const url = URL.createObjectURL(blob);
        try {
          const image = await chargerImage(url);
          if (!estActuel() || op.annulation) return;
          if (doc.largeur !== dimensions?.[0] || doc.hauteur !== dimensions?.[1]) {
            throw new Error('Les dimensions du document ont changé');
          }
          const nom = `Retouche : ${p.titre}`, calque = creerRaster(doc.largeur, doc.hauteur, nom);
          const [gauche, haut, droite, bas] = zoneDessin(p.zone, { x, y, largeur, hauteur });
          calque.ctx2d.save();
          calque.ctx2d.beginPath(); calque.ctx2d.rect(gauche, haut, droite - gauche, bas - haut); calque.ctx2d.clip();
          calque.ctx2d.drawImage(image, x, y, largeur, hauteur);
          calque.ctx2d.restore();
          doc.transaction(ctx.historique, nom, () => {
            doc.calques.push(calque); doc.actifId = calque.id; doc.vierge = false;
          });
          ctx.vue.invalider();
        } finally { URL.revokeObjectURL(url); }
      } }, `${p.titre} · `);
      if (op.annulation) return;
    }
    message(ctx, zones.length === 1 ? 'Zone appliquée' : `${zones.length} zones appliquées`);
  });

  return {
    id: 'retouche-dialogue', libelle: 'Retouche dialoguée', curseur: 'crosshair',
    reinitialiser(ctx) {
      annulerOperation(ctx);
      reinitialiser();
      if (panneau) ctx.actualiserOptions();
    },
    desactiver() { geste = null; panneau = null; },
    panneauOptions(ctx) {
      verifierDimensions(ctx);
      const racine = document.createElement('div');
      racine.className = 'retouche-dialogue';
      const bouton = (texte, action) => {
        const b = document.createElement('button');
        b.type = 'button'; b.textContent = texte; b.onclick = action;
        return b;
      };
      const fil = document.createElement('div');
      fil.className = 'dialogue-fil'; fil.hidden = !historique.length;
      fil.setAttribute('role', 'log'); fil.setAttribute('aria-label', 'Discussion');
      for (const m of historique) {
        const entree = document.createElement('p'), auteur = document.createElement('strong');
        auteur.textContent = m.role === 'user' ? 'Vous' : 'VertIA';
        entree.append(auteur, m.contenu); fil.append(entree);
      }
      const label = document.createElement('label'), saisie = document.createElement('textarea');
      saisie.value = question; saisie.maxLength = 4000;
      saisie.oninput = () => { question = saisie.value; };
      label.append('Votre question', saisie);
      const envoyerBouton = bouton('Envoyer', () => envoyer(ctx));
      const annuler = bouton('Annuler', () => annulerOperation(ctx));
      const actions = document.createElement('div');
      actions.className = 'dialogue-actions'; actions.append(envoyerBouton, annuler);
      const sortie = document.createElement('p');
      sortie.setAttribute('role', 'status');
      racine.append(fil, label, actions, sortie);
      const lignes = propositions.map((p, i) => {
        const ligne = document.createElement('div'), caseZone = document.createElement('input');
        ligne.className = 'dialogue-proposition'; ligne.style.borderColor = couleur(i);
        caseZone.type = 'checkbox'; caseZone.setAttribute('aria-label', `Appliquer ${p.titre}`);
        caseZone.onchange = () => { p.cochee = caseZone.checked; afficher(); };
        const titre = bouton(`${i + 1}. ${p.titre}`, () => choisir(ctx, i));
        const aide = document.createElement('p'); aide.textContent = 'Zone à tracer sur le canevas';
        const texte = document.createElement('textarea');
        texte.setAttribute('aria-label', `Consigne pour ${p.titre}`);
        texte.value = p.prompt; texte.maxLength = 4000;
        texte.oninput = () => { p.prompt = texte.value; };
        ligne.append(caseZone, titre, aide, texte); racine.append(ligne);
        return { bouton: titre, texte, caseZone, aide };
      });
      const appliquerBouton = bouton('Appliquer les zones cochées', () => appliquer(ctx));
      appliquerBouton.hidden = !propositions.length; racine.append(appliquerBouton);
      panneau = { sortie, saisie, envoyer: envoyerBouton, appliquer: appliquerBouton, annuler, lignes };
      afficher();
      queueMicrotask(() => { fil.scrollTop = fil.scrollHeight; });
      return racine;
    },
    dessinerSurimpression(ctx, rendu) {
      const zoom = ctx.vue.zoom;
      propositions.forEach(({ zone }, i) => {
        if (!zone) return;
        const [x, y, droite, bas] = zone;
        rendu.save();
        rendu.strokeStyle = rendu.fillStyle = couleur(i);
        rendu.lineWidth = (i === selection ? 3 : 2) / zoom;
        rendu.strokeRect(x, y, droite - x, bas - y);
        rendu.fillRect(x, y, 22 / zoom, 20 / zoom);
        rendu.fillStyle = '#fff'; rendu.font = `bold ${13 / zoom}px system-ui`;
        rendu.textAlign = 'center'; rendu.textBaseline = 'middle';
        rendu.fillText(String(i + 1), x + 11 / zoom, y + 10 / zoom);
        if (i === selection) {
          for (const [cx, cy] of COINS) {
            const gauche = zone[cx] - 4 / zoom, haut = zone[cy] - 4 / zoom;
            rendu.fillRect(gauche, haut, 8 / zoom, 8 / zoom);
            rendu.strokeRect(gauche, haut, 8 / zoom, 8 / zoom);
          }
        }
        rendu.restore();
      });
    },
    pointeurBas(ctx, e) {
      if (e.button !== 0 || operation) return;
      const point = ctx.vue.coordonnees(e), p = propositions[selection];
      if (!p) return;
      if (!p.zone) { geste = { p, point, zone: null, cochee: p.cochee }; return; }
      const coin = poignee(p.zone, point, 8 / ctx.vue.zoom);
      const contient = ([x1, y1, x2, y2]) => point.x >= x1 && point.x <= x2 && point.y >= y1 && point.y <= y2;
      if (coin >= 0 || contient(p.zone)) {
        geste = { p, point, zone: p.zone, coin, cochee: p.cochee };
      } else {
        const i = propositions.findIndex(c => c.zone && contient(c.zone));
        if (i >= 0) {
          choisir(ctx, i);
          const cible = propositions[i];
          geste = { p: cible, point, zone: cible.zone, coin: -1, cochee: cible.cochee };
        }
      }
    },
    pointeurDeplace(ctx, e) {
      if (!geste || operation) return;
      const { p, point: debut, zone, coin } = geste, point = ctx.vue.coordonnees(e);
      const { largeur, hauteur } = ctx.document;
      if (!zone) {
        if (Math.hypot(point.x - debut.x, point.y - debut.y) < 2 / ctx.vue.zoom && !p.zone) return;
        p.zone = bornerZone([debut.x, debut.y, point.x, point.y], largeur, hauteur);
        p.cochee = true;
      } else if (coin < 0) {
        p.zone = deplacerZone(zone, point.x - debut.x, point.y - debut.y, largeur, hauteur);
      } else {
        const [x, y] = COINS[coin], minX = Math.min(MINIMUM, largeur), minY = Math.min(MINIMUM, hauteur);
        p.zone = redimensionnerZone(zone, coin, {
          x: Math.round(x === 0 ? borner(point.x, 0, zone[2] - minX) : borner(point.x, zone[0] + minX, largeur)),
          y: Math.round(y === 1 ? borner(point.y, 0, zone[3] - minY) : borner(point.y, zone[1] + minY, hauteur))
        });
      }
      afficher(); ctx.vue.invalider();
    },
    pointeurHaut(ctx, e) {
      if (!geste) return;
      if (e.type === 'pointerup') this.pointeurDeplace(ctx, e);
      else {
        geste.p.zone = geste.zone; geste.p.cochee = geste.cochee;
        afficher(); ctx.vue.invalider();
      }
      geste = null;
    }
  };
}

export default creerDialogue();

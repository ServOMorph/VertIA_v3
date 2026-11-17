async function requete(url, options = {}) {
  const response = await fetch(url, { signal: AbortSignal.timeout(30000), ...options });
  if (!response.ok) {
    const erreur = await response.json().catch(() => ({}));
    const detail = erreur.detail;
    throw new Error(typeof detail === "string" ? detail : detail?.message || `Erreur HTTP ${response.status}.`);
  }
  return response;
}

async function demande(capacite, params, statut) {
  const response = await requete("/api/v1/demandes", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session: "vertia", capacite, params }),
  });
  const { id } = await response.json();
  while (true) {
    const etat = await (await requete(`/api/v1/demandes/${encodeURIComponent(id)}`)).json();
    if (["livre", "valide"].includes(etat.etat)) return id;
    if (["echec", "annule", "plafond"].includes(etat.etat)) {
      const messages = {
        gpu_occupe: "GPU occupé ou mémoire insuffisante. Réessayez plus tard.",
        pause: "Le GPU est en pause à la demande de l’utilisateur.",
        moteur: "Échec du moteur audio.",
      };
      throw new Error(messages[etat.motif_code] || etat.erreur || "Demande interrompue.");
    }
    statut.textContent = etat.etat === "actif" ? "Traitement audio en cours…" : "En attente du GPU…";
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
}

function fichier(id, index = 0) {
  return `/api/v1/demandes/${encodeURIComponent(id)}/fichiers/${index}`;
}

function telechargement(id, url, nom) {
  const lien = document.getElementById(id);
  lien.href = url;
  lien.download = nom;
  lien.hidden = false;
}

function formulaire(id, traiter) {
  const form = document.getElementById(id);
  const statut = document.getElementById(`${id}-statut`);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const bouton = form.querySelector("button[type=submit]");
    bouton.disabled = true;
    statut.textContent = "Envoi…";
    try {
      await traiter(new FormData(form), statut);
      statut.textContent = "Terminé.";
    } catch (error) {
      statut.textContent = error.message || "Le portail est injoignable.";
    } finally {
      bouton.disabled = false;
    }
  });
}

formulaire("synthese", async (data, statut) => {
  const audio = document.getElementById("audio");
  audio.pause();
  audio.hidden = true;
  audio.removeAttribute("src");
  document.getElementById("audio-telecharger").hidden = true;
  const params = Object.fromEntries(data);
  for (const key of ["exageration", "cfg", "temperature", "vitesse", "seed"]) params[key] = Number(params[key]);
  const id = await demande("voix.generer", params, statut);
  audio.src = fichier(id);
  audio.hidden = false;
  telechargement("audio-telecharger", fichier(id), "voix_1.wav");
});

formulaire("transcription", async (data, statut) => {
  document.getElementById("texte-transcrit").textContent = "";
  document.getElementById("texte-telecharger").hidden = true;
  const audio = data.get("fichier");
  const extension = audio.name.split(".").pop().toLowerCase();
  if (!["wav", "mp3", "flac", "ogg", "m4a"].includes(extension)) throw new Error("Format audio non pris en charge.");
  if (audio.size > 200 * 1024 ** 2) throw new Error("Le fichier dépasse 200 Mio.");
  const upload = await requete(`/api/v1/inbox?extension=${encodeURIComponent(extension)}`, {
    method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: audio,
  });
  const { nom } = await upload.json();
  const id = await demande("voix.transcrire", { source: nom, modele: data.get("modele"), langue: data.get("langue") }, statut);
  document.getElementById("texte-transcrit").textContent = await (await requete(fichier(id))).text();
  telechargement("texte-telecharger", fichier(id), "transcription.txt");
});

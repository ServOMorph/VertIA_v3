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
        moteur: "Échec du moteur musique.",
      };
      throw new Error(messages[etat.motif_code] || etat.erreur || "Demande interrompue.");
    }
    statut.textContent = etat.etat === "actif" ? "Création musicale en cours…" : "En attente du GPU…";
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

formulaire("generation", async (data, statut) => {
  const audio = document.getElementById("audio");
  audio.pause();
  audio.hidden = true;
  audio.removeAttribute("src");
  document.getElementById("audio-telecharger").hidden = true;
  document.getElementById("metadata-telecharger").hidden = true;
  const params = Object.fromEntries(data);
  params.instrumental = data.has("instrumental");
  params.lm = data.has("lm");
  if (params.instrumental && params.paroles.trim()) throw new Error("Décochez Instrumental pour utiliser des paroles.");
  for (const key of ["duree", "seed", "etapes"]) params[key] = Number(params[key]);
  if (params.bpm === "") delete params.bpm;
  else params.bpm = Number(params.bpm);
  const id = await demande("musique.generer", params, statut);
  audio.src = fichier(id);
  audio.hidden = false;
  telechargement("audio-telecharger", fichier(id), "musique_1.wav");
  telechargement("metadata-telecharger", fichier(id, 1), "musique_1.json");
});

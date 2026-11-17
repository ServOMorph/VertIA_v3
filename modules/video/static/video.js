async function requete(url, options = {}) {
  const response = await fetch(url, { signal: AbortSignal.timeout(30000), ...options });
  if (!response.ok) {
    const erreur = await response.json().catch(() => ({}));
    const detail = erreur.detail;
    throw new Error(typeof detail === "string" ? detail : detail?.message || `Erreur HTTP ${response.status}.`);
  }
  return response;
}

async function demande(params, statut) {
  const response = await requete("/api/v1/demandes", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session: "vertia", capacite: "video.generer", params }),
  });
  const { id } = await response.json();
  while (true) {
    const etat = await (await requete(`/api/v1/demandes/${encodeURIComponent(id)}`)).json();
    if (["livre", "valide"].includes(etat.etat)) return id;
    if (["echec", "annule", "plafond"].includes(etat.etat)) {
      const messages = {
        gpu_occupe: "GPU occupé ou mémoire insuffisante. Réessayez plus tard.",
        pause: "Le GPU est en pause à la demande de l’utilisateur.",
        moteur: "Échec du moteur vidéo.",
      };
      throw new Error(messages[etat.motif_code] || etat.erreur || "Demande interrompue.");
    }
    statut.textContent = etat.etat === "actif" ? "Création vidéo en cours… environ 1 h pour 81 images." : "En attente du GPU…";
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

function initialiser() {
  const form = document.getElementById("generation");
  const mode = form.elements.namedItem("mode");
  const image = form.elements.namedItem("image");
  mode.addEventListener("change", () => {
    const i2v = mode.value === "i2v";
    document.getElementById("image-champ").hidden = !i2v;
    image.disabled = !i2v;
    image.required = i2v;
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const bouton = form.querySelector("button[type=submit]");
    const statut = document.getElementById("generation-statut");
    const video = document.getElementById("video");
    bouton.disabled = true;
    statut.textContent = "Envoi…";
    video.pause();
    video.hidden = true;
    video.removeAttribute("src");
    document.getElementById("video-telecharger").hidden = true;
    document.getElementById("metadata-telecharger").hidden = true;
    try {
      const data = new FormData(form);
      const params = Object.fromEntries(data);
      delete params.image;
      for (const key of ["seed", "images"]) params[key] = Number(params[key]);
      if (params.etapes === "") delete params.etapes;
      else params.etapes = Number(params.etapes);
      if (params.mode === "i2v") {
        const source = data.get("image");
        if (!source || !source.size) throw new Error("Une image est requise en i2v.");
        const extension = source.name.split(".").pop().toLowerCase();
        if (!["png", "jpg", "jpeg", "webp"].includes(extension)) throw new Error("Format image non pris en charge.");
        if (source.size > 50 * 1024 ** 2) throw new Error("Le fichier dépasse 50 Mio.");
        const upload = await requete(`/api/v1/inbox?extension=${encodeURIComponent(extension)}`, {
          method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: source,
        });
        params.image = (await upload.json()).nom;
      }
      const id = await demande(params, statut);
      video.src = fichier(id);
      video.hidden = false;
      telechargement("video-telecharger", fichier(id), "video_1.mp4");
      telechargement("metadata-telecharger", fichier(id, 1), "video_1.json");
      statut.textContent = "Terminé.";
    } catch (error) {
      statut.textContent = error.message || "Le portail est injoignable.";
    } finally {
      bouton.disabled = false;
    }
  });
}

initialiser();

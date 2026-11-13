import { api } from "./api.js";

export async function initSetup() {
  const dialog = document.getElementById("installation-dialog");
  const form = document.getElementById("installation-form");
  const status = document.getElementById("installation-statut");
  const results = document.getElementById("installation-resultats");
  const diagnostic = document.getElementById("installation-diagnostic");
  const save = form.querySelector('[type="submit"]');
  const fields = ["ollama_url", "default_model", "comfy_dir", "comfy_port", "acestep_dir", "acestep_port"];
  let busy = false;
  let dismissed = false;
  form.addEventListener("input", () => {
    results.replaceChildren();
    status.textContent = "Réglages modifiés. Vérifiez les valeurs affichées puis enregistrez-les pour le prochain démarrage.";
  });

  function values() {
    return Object.fromEntries(fields.map((key) => [key, key.endsWith("_port")
      ? Number(form.elements[key].value) : form.elements[key].value.trim()]));
  }

  async function load() {
    try {
      const data = await api("/installation", { timeout: 5000 });
      for (const key of fields) form.elements[key].value = data.configuration[key];
      status.textContent = data.redemarrage_requis ? "Réglages enregistrés. Arrêtez puis relancez VertIA pour les appliquer." : "Vous pouvez vérifier les moteurs sans les démarrer.";
      if (!data.accueil_termine && !dismissed && !dialog.open) dialog.showModal();
    } catch (error) {
      status.textContent = `Réglages indisponibles : ${error.message}`;
    }
  }

  document.getElementById("ouvrir-installation").addEventListener("click", () => {
    if (!dialog.open) dialog.showModal();
    load();
  });
  document.getElementById("installation-fermer").addEventListener("click", async () => {
    dismissed = true;
    dialog.close();
    document.querySelector('[data-toggle="chat"][aria-pressed="false"]')?.click();
    document.getElementById("chat-message").focus();
    try {
      await api("/installation/terminer", { method: "POST", timeout: 5000 });
      document.getElementById("accueil-avertissement").textContent = "";
    } catch (error) {
      document.getElementById("accueil-avertissement").textContent = `Accueil fermé, mais sa mémorisation a échoué : ${error.message}. Il pourra réapparaître au prochain lancement.`;
    }
  });

  async function run(operation) {
    if (busy) return;
    if (!form.checkValidity()) document.getElementById("installation-chemins").open = true;
    if (!form.reportValidity()) return;
    busy = true;
    diagnostic.disabled = save.disabled = true;
    for (const key of fields) form.elements[key].readOnly = true;
    try { await operation(); }
    catch (error) { status.textContent = error.message; }
    finally {
      busy = false; diagnostic.disabled = save.disabled = false;
      for (const key of fields) form.elements[key].readOnly = false;
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    run(async () => {
      const data = await api("/installation", { method: "PUT", body: values() });
      status.textContent = data.redemarrage_requis
        ? "Réglages enregistrés. Arrêtez puis relancez VertIA pour les appliquer. Les tâches actuelles gardent leurs réglages."
        : "Réglages enregistrés et déjà actifs.";
    });
  });

  diagnostic.addEventListener("click", () => run(async () => {
    status.textContent = "Vérification des adresses et chemins affichés…";
    results.replaceChildren();
    const data = await api("/installation/diagnostic", { method: "POST", body: values() });
    function line(text) {
      const p = document.createElement("p");
      p.textContent = text;
      results.append(p);
    }
    line(data.ollama.joignable
      ? `Chat : Ollama joignable. Modèle choisi ${data.ollama.modele_choisi_present ? "détecté" : "absent : choisissez un modèle installé ou installez-le dans Ollama"}.`
      : "Chat : Ollama ne répond pas encore. Consultez son état en haut de l’écran et vérifiez son adresse locale ; VertIA tente de le démarrer au lancement.");
    const options = (data.ollama.modeles || []).map((name) => {
      const option = document.createElement("option"); option.value = name; return option;
    });
    document.getElementById("installation-modeles").replaceChildren(...options);
    line(`ComfyUI : ${data.comfy.joignable ? "joignable" : "arrêté ou inaccessible"}.`);
    for (const [name, check] of [["Installation ComfyUI", data.comfy.installation], ["Image Qwen", data.comfy.image], ["Vidéo Wan", data.comfy.video], ["Installation ACE-Step", data.ace.installation]]) {
      line(`${name} : ${check.present ? "fichiers attendus présents" : "fichiers manquants"}.`);
      if (!check.present) {
        const details = document.createElement("details");
        const summary = document.createElement("summary"); summary.textContent = "Voir les fichiers attendus";
        const list = document.createElement("ul");
        for (const name of check.manquants) { const li = document.createElement("li"); li.textContent = name; list.append(li); }
        details.append(summary, list); results.append(details);
      }
    }
    line(`ACE-Step : ${data.ace.joignable ? "joignable ; une instance lancée séparément doit être arrêtée avant de créer une musique" : "arrêté ou inaccessible"}. Configuration du checkpoint turbo ${data.ace.checkpoint_present ? "détectée" : "non détectée"} ; poids non vérifiés.`);
    status.textContent = data.limite;
  }));
  await load();
}

import { api } from "./api.js";
import { on } from "./events.js";

export function initOllama(onReady) {
  const badge = document.getElementById("etat-ollama");
  let revision = -1;
  let ready = false;
  let connection = 0;
  function render(state) {
    if (state.revision < revision) return;
    revision = state.revision;
    const available = state.etat === "pret";
    badge.dataset.etat = available ? "ok" : state.etat === "demarrage" ? "attente" : "ko";
    let text = state.message;
    if (available && Array.isArray(state.modeles_charges)) {
      text += state.modeles_charges.length
        ? ` · chargé : ${state.modeles_charges.join(", ")}`
        : " · aucun modèle chargé";
    }
    const preload = state.prechargement;
    if (available && preload?.message) text += ` · ${preload.message}`;
    if (available && ["attente", "chargement"].includes(preload?.etat)) badge.dataset.etat = "attente";
    badge.textContent = text;
    badge.title = text;
    if (available && !ready) onReady?.();
    ready = available;
  }
  on("ollama.etat", render);
  return {
    async reconnect() {
      const previous = revision;
      const current = ++connection;
      try {
        const state = await api("/ollama/etat", { timeout: 5000 });
        if (current === connection) render(state);
      }
      catch {
        if (current === connection && revision === previous) this.disconnected();
      }
    },
    disconnected() {
      connection++;
      revision = -1;
      ready = false;
      badge.dataset.etat = "ko";
      badge.textContent = "Ollama : état inconnu · connexion à VertIA perdue";
      badge.title = badge.textContent;
    },
  };
}

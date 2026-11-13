import { api } from "./api.js";
import { on } from "./events.js";

export async function initResources() {
  const zone = document.getElementById("memoire-zone");
  const status = document.createElement("p");
  status.setAttribute("role", "status");
  const content = document.createElement("div");
  zone.replaceChildren(status, content);
  let resources = {};
  let jobs = [];
  let connected = false;
  let resourceRevision = 0;
  const labels = { attente: "En attente", actif: "En cours", termine: "Terminé", annule: "Annulé", interrompu: "Interrompu", erreur: "Erreur" };

  function node(tag, text, parent = content) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    parent.append(element);
    return element;
  }

  function button(text, action, parent = content) {
    const element = node("button", text, parent);
    element.type = "button";
    element.className = "toggle";
    element.addEventListener("click", async () => {
      element.disabled = true;
      try {
        await action();
        status.textContent = "Action effectuée.";
        await refresh();
      } catch (error) { status.textContent = error.message; }
      finally { element.disabled = false; }
    });
  }

  function gauge(label, value, limit, parent = content) {
    if (!value) { node("p", `${label} : mesure indisponible`, parent); return; }
    const row = node("label", `${label} : ${value.used_mb.toFixed(0)} / ${value.total_mb.toFixed(0)} Mo (${value.percent.toFixed(0)} %)`, parent);
    const meter = node("meter", undefined, row);
    meter.min = 0;
    meter.max = 100;
    meter.high = limit || 100;
    meter.value = value.percent;
    meter.setAttribute("aria-label", label);
  }

  function render() {
    if (content.contains(document.activeElement) && document.activeElement.tagName === "INPUT") return;
    content.replaceChildren();
    gauge("RAM", resources.ram, resources.limits?.ram);
    if (!resources.gpus?.length) gauge("VRAM", null);
    for (const [index, gpu] of (resources.gpus || []).entries()) gauge(`VRAM GPU ${index + 1}`, gpu, resources.limits?.vram);
    for (const warning of resources.warnings || []) node("p", warning).className = "muted";
    node("p", `Moteur actif : ${resources.engine || "aucun"}`);
    const controls = node("div");
    controls.className = "resource-actions";
    button("Tout libérer", () => api("/ressources/liberer", { method: "POST" }), controls);
    for (const engine of resources.engines || []) {
      button(`Décharger ${engine}`, () => api(`/ressources/liberer?engine=${encodeURIComponent(engine)}`, { method: "POST" }), controls);
    }
    node("h3", "Modèles Ollama chargés");
    if (!resources.models?.length) node("p", "Aucun modèle chargé connu.").className = "muted";
    for (const model of resources.models || []) {
      const name = model.name || model.model;
      const row = node("div");
      row.className = "resource-item";
      node("span", name, row);
      button(`Décharger ${name}`, () => api(`/ressources/liberer?engine=ollama&modele=${encodeURIComponent(name)}`, { method: "POST" }), row);
    }
    if (resources.processes?.length) {
      const details = node("details");
      node("summary", "VRAM par processus", details);
      for (const process of resources.processes) node("p", `PID ${process.pid} : ${process.used_mb.toFixed(0)} Mo`, details);
    }
    node("h3", "Tâches GPU");
    node("p", "La priorité la plus élevée passe en premier. Les réponses interrompues se renvoient depuis la discussion.").className = "muted";
    if (!jobs.length) node("p", "Aucune tâche.");
    for (const job of jobs) {
      const row = node("article");
      row.className = "resource-item resource-job";
      row.dataset.jobId = job.id;
      node("p", `${job.kind} · ${job.engine} · ${labels[job.status] || job.status} · ${job.progress.toFixed(0)} %`, row);
      if (job.error) node("p", job.error, row);
      if (["attente", "actif"].includes(job.status)) button("Annuler", () => api(`/jobs/${job.id}/annuler`, { method: "POST" }), row);
      if (job.status === "attente") {
        const label = node("label", "Priorité ", row);
        const input = node("input", undefined, label);
        input.type = "number";
        input.min = -100;
        input.max = 100;
        input.value = job.priority;
        button("Appliquer", () => {
          if (!input.checkValidity()) throw new Error("La priorité doit être comprise entre -100 et 100.");
          return api(`/jobs/${job.id}`, { method: "PATCH", body: { priority: Number(input.value) } });
        }, row);
      }
      if (job.resumable && ["interrompu", "annule", "erreur"].includes(job.status)) {
        button("Relancer", () => api(`/jobs/${job.id}/reprendre`, { method: "POST" }), row);
      }
    }
  }

  async function refresh() {
    const revision = resourceRevision;
    const [state, list] = await Promise.all([api("/ressources"), api("/jobs")]);
    resources = revision === resourceRevision ? state : { ...state, ...resources };
    const merged = new Map(list.map((job) => [job.id, job]));
    for (const job of jobs) {
      if ((job.revision || 0) > (merged.get(job.id)?.revision ?? -1)) merged.set(job.id, job);
    }
    jobs = [...merged.values()].slice(0, 200);
    render();
  }

  on("ressources.maj", (state) => { resourceRevision++; resources = { ...resources, ...state }; render(); });
  on("ressources.erreur", (state) => { status.textContent = state.erreur; });
  on("jobs.maj", (job) => {
    const previous = jobs.find((item) => item.id === job.id);
    if ((previous?.revision || 0) > (job.revision || 0)) return;
    jobs = [job, ...jobs.filter((item) => item.id !== job.id)].slice(0, 200);
    render();
  });
  // Les événements sont enregistrés avant la connexion SSE et le premier instantané.
  return { reconnect: async () => {
    try { await refresh(); if (connected) status.textContent = "État actualisé."; connected = true; }
    catch (error) { status.textContent = error.message; }
  } };
}

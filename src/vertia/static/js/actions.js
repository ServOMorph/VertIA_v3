import { api } from "./api.js";
import { on } from "./events.js";

export function createActionCards(report, refresh) {
  const drafts = new Map();
  function render(zone, actions) {
    for (const action of actions) {
      const message = zone.querySelector(`[data-message-id="${action.message_id}"]`);
      if (!message) continue;
      const form = document.createElement("form");
      form.className = "action-card";
      form.dataset.actionId = action.id;
      form.dataset.jobId = action.job_id || "";
      form.dataset.jobRevision = String(action.job?.revision ?? -1);
      const title = document.createElement("h3");
      const music = action.tool === "musique_ace";
      const video = action.tool === "video_wan";
      title.textContent = music ? "Composer une musique" : video ? action.parameters.mode === "i2v" ? "Animer une image" : "Créer une vidéo" : action.parameters.mode === "edit" ? "Modifier une image" : "Créer une image";
      const state = document.createElement("p");
      state.className = "action-status muted";
      state.setAttribute("role", "status");
      state.textContent = action.job ? `${action.job.status} · ${Math.round(action.job.progress)} %${action.job.error ? ` · ${action.job.error}` : ""}` : action.status === "annulee" ? "Carte annulée" : action.status === "validee" ? "Génération envoyée dans la file." : "Vérifiez le prompt et les paramètres avant de lancer.";
      form.append(title, state);
      if (action.parameters.references?.length) {
        const refs = document.createElement("p");
        refs.className = "action-references";
        refs.textContent = `Images de référence : ${action.parameters.references.join(", ")}. ${video ? "L’image est ajustée et recadrée au format vidéo choisi." : "En édition, le format est calculé depuis l’image source (résolution Qwen 1024)."}`;
        form.append(refs);
      }
      const params = action.status === "proposee" ? drafts.get(action.id) || action.parameters : action.parameters;
      const fields = {};
      const definitions = music ? [
        ["prompt", "Demande", "textarea"], ["titre", "Titre", "text"],
        ["caption", "Description musicale en anglais (5 à 8 termes)", "textarea"],
        ["paroles", "Paroles balisées [verse] / [chorus]", "textarea"],
        ["instrumental", "Instrumental (paroles vides)", "checkbox"],
        ["langue", "Langue du chant", "select"],
        ["bpm", "Tempo (BPM)", "number", 30, 240, 1],
        ["duree", "Durée (secondes)", "number", 20, 135, 1],
        ["seed", "Graine", "number", 0, 4294967295, 1],
      ] : video ? [
        ["prompt", "Sujet et mouvement", "textarea"], ["negatif", "À éviter", "textarea"],
        ["largeur", "Largeur", "number", 256, 960, 32], ["hauteur", "Hauteur", "number", 256, 960, 32],
        ["images", "Nombre d’images (49 ≈ 2 secondes)", "number", 17, 73, 4],
        ["etapes", "Étapes", "number", 1, 30, 1], ["seed", "Graine", "number", 0, 9007199254740991, 1],
      ] : [
        ["prompt", "Prompt", "textarea"], ["negatif", "À éviter", "textarea"],
        ["largeur", "Largeur", "number", 256, 1536, 32], ["hauteur", "Hauteur", "number", 256, 1536, 32],
        ["etapes", "Étapes", "number", 1, 30, 1], ["seed", "Graine", "number", 0, 9007199254740991, 1],
      ];
      if (music) {
        const help = document.createElement("p");
        help.className = "muted";
        help.textContent = "MP3 · 8 étapes · un morceau. Adaptez les paroles à la durée (2,5 s par ligne + 3 s par section, estimation). En français, maximum estimé de 12 syllabes par ligne. Pour un instrumental : videz les paroles et indiquez instrumental dans la description. Cover audio indisponible.";
        form.append(help);
      }
      if (video) {
        const help = document.createElement("p");
        help.className = "muted";
        help.textContent = "MP4 muet · 24 images/s · une vidéo de 0,7 à 3 secondes. Surface maximale 960 × 544 pixels. Le calcul peut prendre plusieurs minutes ; la faisabilité sur votre machine reste à mesurer.";
        form.append(help);
      }
      for (const [key, labelText, type, min, max, step] of definitions) {
        const label = document.createElement("label");
        label.textContent = labelText;
        const input = document.createElement(["textarea", "select"].includes(type) ? type : "input");
        if (type === "select") {
          for (const [value, text] of [["fr", "Français"], ["en", "Anglais"]]) {
            const option = document.createElement("option");
            option.value = value; option.textContent = text; input.append(option);
          }
        }
        input.name = key;
        input.value = params[key] ?? "";
        if (type === "number") Object.assign(input, { type, min, max, step, required: true });
        else if (type === "checkbox") { input.type = type; input.checked = Boolean(params[key]); }
        else if (type !== "select") {
          if (type === "text") input.type = "text";
          input.rows = ["prompt", "paroles"].includes(key) ? 4 : 2;
          input.maxLength = ({ titre: 120, caption: 400, paroles: 6000, prompt: music ? 1000 : 4000 })[key] || 2000;
          input.required = ["prompt", "titre", "caption"].includes(key);
        }
        input.disabled = action.status !== "proposee" || action.parameters.mode === "edit" && ["largeur", "hauteur"].includes(key);
        fields[key] = input;
        input.addEventListener("input", () => drafts.set(action.id, values()));
        label.append(input);
        form.append(label);
      }
      function values() {
        const result = { ...action.parameters };
        for (const [key, input] of Object.entries(fields)) result[key] = input.type === "number" ? Number(input.value) : input.type === "checkbox" ? input.checked : input.value;
        return result;
      }
      const controls = document.createElement("div");
      controls.className = "chat-actions";
      async function change(suffix, method, withParams) {
        for (const button of controls.querySelectorAll("button")) button.disabled = true;
        try {
          await api(`/actions/${action.id}${suffix}`, { method, ...(withParams ? { body: { parameters: values() } } : {}) });
          drafts.delete(action.id);
          await refresh();
        } catch (error) { report(error); state.textContent = error.message; }
        finally { for (const button of controls.querySelectorAll("button")) button.disabled = false; }
      }
      if (action.status === "proposee") {
        for (const [label, suffix, method, withParams] of [["Lancer la génération", "/valider", "POST", true], ["Enregistrer les modifications", "", "PATCH", true], ["Annuler la carte", "/annuler", "POST", false]]) {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "btn btn--ghost";
          button.textContent = label;
          button.addEventListener("click", () => { if (!withParams || form.reportValidity()) change(suffix, method, withParams); });
          controls.append(button);
        }
      }
      form.addEventListener("submit", (event) => event.preventDefault());
      form.append(controls);
      for (const [index] of (action.result?.images || []).entries()) {
        const image = document.createElement("img");
        image.src = `/api/actions/${encodeURIComponent(action.id)}/images/${index}`;
        image.alt = action.parameters.prompt;
        image.loading = "lazy";
        image.className = "action-image";
        form.append(image);
      }
      if (music) {
        for (const [index] of (action.result?.audios || []).entries()) {
          const audio = document.createElement("audio");
          audio.controls = true;
          audio.preload = "metadata";
          const fileId = action.result.files?.[index];
          audio.src = fileId ? `/api/fichiers/${encodeURIComponent(fileId)}/contenu` : `/api/actions/${encodeURIComponent(action.id)}/medias/${index}`;
          form.append(audio);
        }
      }
      if (video) {
        for (const [index] of (action.result?.videos || []).entries()) {
          const player = document.createElement("video");
          player.controls = true;
          player.preload = "metadata";
          player.className = "action-image";
          const fileId = action.result.files?.[index];
          player.src = fileId ? `/api/fichiers/${encodeURIComponent(fileId)}/contenu` : `/api/actions/${encodeURIComponent(action.id)}/medias/${index}`;
          form.append(player);
        }
      }
      message.append(form);
    }
  }
  on("jobs.maj", (job) => {
    for (const card of document.querySelectorAll(".action-card")) {
      if (card.dataset.jobId === job.id || card.dataset.actionId === job.payload?.action_id) {
        if (card.dataset.jobId === job.id && Number(card.dataset.jobRevision) > (job.revision ?? 0)) continue;
        card.dataset.jobId = job.id;
        card.dataset.jobRevision = String(job.revision ?? 0);
        card.querySelector(".action-status").textContent = `${job.status} · ${Math.round(job.progress)} %${job.error ? ` · ${job.error}` : ""}`;
      }
    }
  });
  return { render };
}

export async function initTools() {
  const zone = document.getElementById("outils-zone");
  try {
    const tools = await api("/outils");
    zone.replaceChildren();
    for (const tool of tools) {
      const title = document.createElement("h3");
      title.textContent = tool.name;
      const description = document.createElement("p");
      description.textContent = tool.description;
      zone.append(title, description);
    }
  } catch (error) { zone.textContent = error.message; }
}

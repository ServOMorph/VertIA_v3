import { api } from "./api.js";
import { on } from "./events.js";

export function createFiles(report) {
  const zone = document.getElementById("fichiers-zone");
  const attachments = document.getElementById("chat-pieces-jointes");
  const composer = document.getElementById("chat-form");
  const selected = new Map();
  let conversation = null;
  let files = [];
  let revision = 0;
  const dragType = "application/x-vertia-file";

  function button(text, handler) {
    const node = document.createElement("button");
    node.type = "button";
    node.className = "btn btn--ghost";
    node.textContent = text;
    node.addEventListener("click", () => Promise.resolve().then(handler).catch(report));
    return node;
  }
  function renderAttachments() {
    attachments.replaceChildren();
    for (const file of selected.values()) {
      const chip = document.createElement("span");
      chip.className = "file-attachment";
      chip.textContent = `${file.type} · ${file.id.slice(0, 8)} `;
      chip.append(button("Retirer", () => { selected.delete(file.id); renderAttachments(); }));
      attachments.append(chip);
    }
  }
  function use(file) {
    if (!selected.has(file.id) && selected.size >= 3) throw Error("Trois pièces jointes maximum.");
    selected.set(file.id, file);
    renderAttachments();
    document.getElementById("chat-message").focus();
  }
  function render() {
    zone.replaceChildren();
    const hint = document.createElement("p");
    hint.className = "muted";
    hint.textContent = !conversation ? "Choisissez une discussion pour voir ses fichiers." : !files.length ? "Aucun fichier généré dans cette discussion." : "Glissez un fichier vers le message ou utilisez le bouton de la carte.";
    zone.append(hint);
    const gallery = document.createElement("div");
    gallery.className = "file-gallery";
    for (const file of files) {
      const card = document.createElement("article");
      card.className = "file-card";
      card.dataset.fileId = file.id;
      card.draggable = true;
      card.addEventListener("dragstart", (event) => { event.dataTransfer.setData(dragType, file.id); event.dataTransfer.effectAllowed = "copy"; });
      const url = `/api/fichiers/${encodeURIComponent(file.id)}/contenu`;
      const media = document.createElement(file.type === "texte" ? "pre" : file.type === "image" ? "img" : file.type === "audio" ? "audio" : "video");
      if (file.type === "texte") { media.className = "file-text"; media.textContent = file.name; }
      else media.src = url;
      if (file.type === "image") { media.alt = file.prompt; media.loading = "lazy"; }
      else if (file.type !== "texte") { media.controls = true; media.preload = "metadata"; media.setAttribute("aria-label", file.prompt || file.type); }
      const title = document.createElement("p");
      title.className = "file-prompt";
      title.textContent = file.prompt || file.name;
      const info = document.createElement("small");
      info.className = "muted";
      info.textContent = `${file.type} · ${Math.ceil(file.size / 1024)} Ko · ${file.id.slice(0, 8)}`;
      const controls = document.createElement("div");
      controls.className = "chat-actions";
      for (const [label, href] of [["Ouvrir", url], ["Télécharger", `${url}?telecharger=true`]]) {
        const link = document.createElement("a");
        link.className = "btn btn--ghost";
        link.textContent = label;
        link.href = href;
        if (label === "Ouvrir") { link.target = "_blank"; link.rel = "noopener"; }
        else link.download = file.name;
        controls.append(link);
      }
      controls.append(button("Ouvrir le dossier", () => api(`/fichiers/${file.id}/dossier`, { method: "POST" })), button("Utiliser dans le chat", () => use(file)));
      card.append(media, title, info, controls);
      gallery.append(card);
    }
    zone.append(gallery);
  }
  async function load(id) {
    const token = ++revision;
    if (conversation !== id) { selected.clear(); renderAttachments(); files = []; }
    conversation = id;
    render();
    if (!id) return;
    const result = await api(`/conversations/${id}/fichiers`);
    if (token !== revision) return;
    files = result;
    for (const key of selected.keys()) if (!files.some((f) => f.id === key)) selected.delete(key);
    renderAttachments();
    render();
  }
  composer.addEventListener("dragover", (event) => {
    if (event.dataTransfer.types.includes(dragType)) { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; }
  });
  composer.addEventListener("drop", (event) => {
    if (!event.dataTransfer.types.includes(dragType)) return;
    event.preventDefault();
    const file = files.find((f) => f.id === event.dataTransfer.getData(dragType));
    if (!file) return report(Error("Ce fichier appartient à une autre discussion."));
    try { use(file); } catch (error) { report(error); }
  });
  on("fichiers.maj", (data) => { if (data.conversation_id === conversation) load(conversation).catch(report); });
  return { load, ids: () => [...selected.keys()], clear: (ids) => { for (const key of ids) selected.delete(key); renderAttachments(); } };
}

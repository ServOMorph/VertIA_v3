import { api } from "./api.js";
import { on } from "./events.js";
import { MarkdownStream, renderMarkdown } from "./markdown.js";
import { createActionCards } from "./actions.js";
import { createFiles } from "./files.js";
import { createNavigation } from "./navigation.js";
import { setPanel } from "./panels.js";

export async function initChat() {
  const el = (id) => document.getElementById(id);
  const zone = el("chat-zone");
  const status = el("chat-statut");
  let selected = null;
  let folders = [];
  let queue = { actif: null, attente: [] };
  let editingFolder = null;
  let loading = 0;
  let fetching = false;
  let buffered = [];
  const streams = new Map();
  const contents = new Map();

  function icon(paths) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    for (const path of paths) {
      const node = document.createElementNS("http://www.w3.org/2000/svg", "path");
      node.setAttribute("d", path);
      svg.append(node);
    }
    return svg;
  }
  const send = el("envoyer-message");
  send.setAttribute("aria-label", "Envoyer");
  send.title = "Envoyer le message";
  send.replaceChildren(icon(["M12 19V5M5 12l7-7 7 7"]));
  const modelLabel = el("modeles").closest("label");
  modelLabel.classList.add("chat-compose-model");
  el("chat-form").querySelector(".chat-actions").prepend(modelLabel);

  function report(error) { status.textContent = error.message || String(error); }
  const files = createFiles(report);
  const cards = createActionCards(report, () => loadConversation(selected));
  const navigation = createNavigation({ open: loadConversation, editFolder: folderDialog, refresh: refreshLists, report });
  function listen(id, type, handler) {
    el(id).addEventListener(type, async (event) => {
      try { await handler(event); } catch (error) { report(error); }
    });
  }
  function option(select, value, label) {
    select.add(new Option(label, value));
  }
  function queueState(data) {
    queue = data;
    const active = data.actif?.conversation_id === selected;
    const summary = Boolean(selected) && data.resume === selected;
    const waiting = data.attente.filter((j) => j.conversation_id === selected).length;
    el("stop-chat").disabled = !active && !summary && waiting === 0;
    status.textContent = `${active ? "Réponse en cours. " : ""}${summary ? "Actualisation du résumé. " : ""}${waiting ? `${waiting} message(s) en attente. ` : ""}${!active && !summary && !waiting ? "Prêt." : "Vous pouvez envoyer le message suivant."}`;
  }
  async function refreshLists() {
    const [conversations, loadedFolders] = await Promise.all([api("/conversations"), api("/dossiers")]);
    folders = loadedFolders;
    const select = el("conversations");
    select.replaceChildren();
    option(select, "", "Nouvelle discussion");
    for (const c of conversations) option(select, c.id, `${c.ephemere ? "[Éphémère] " : ""}${c.titre}`);
    select.value = selected || "";
    const folderSelect = el("dossiers");
    const oldFolder = folderSelect.value;
    folderSelect.replaceChildren();
    option(folderSelect, "", "Sans dossier");
    for (const f of folders) option(folderSelect, f.id, f.nom);
    folderSelect.value = selected ? conversations.find((c) => c.id === selected)?.dossier_id || "" : oldFolder;
    if (selected) el("titre-chat").textContent = conversations.find((c) => c.id === selected)?.titre || "Discussion";
    navigation.update(folders, conversations);
  }
  function messageNode(message) {
    const article = document.createElement("article");
    article.className = `message message--${message.role}`;
    article.dataset.messageId = message.id;
    const label = document.createElement("strong");
    label.className = "message-author";
    label.textContent = message.role === "user" ? "Vous" : "VertIA";
    const body = document.createElement("div");
    body.className = "message-content";
    const state = document.createElement("small");
    state.className = "muted message-status";
    const states = { attente: "En attente", actif: "En cours", arrete: "Arrêté", annule: "Annulé", interrompu: "Interrompu au redémarrage", erreur: "Erreur" };
    state.textContent = message.erreur || states[message.statut] || "";
    if (message.role === "user") body.textContent = message.contenu;
    else renderMarkdown(body, message.contenu);
    const tools = document.createElement("div");
    tools.className = "message-tools";
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "message-copy";
    const copyLabel = message.role === "user" ? "Copier le message utilisateur" : "Copier la réponse de VertIA";
    copy.setAttribute("aria-label", copyLabel);
    copy.title = copyLabel;
    copy.append(icon(["M9 8V5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-3", "M5 8h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2Z"]));
    const feedback = document.createElement("span");
    feedback.className = "message-copy-status";
    feedback.setAttribute("role", "status");
    feedback.setAttribute("aria-live", "polite");
    copy.addEventListener("click", async () => {
      const text = message.role === "assistant"
        ? contents.get(message.id)?.chunks.join("") ?? message.contenu
        : message.contenu;
      copy.disabled = true;
      try {
        await navigator.clipboard.writeText(text);
        feedback.textContent = "Copié";
      } catch {
        feedback.textContent = "Copie indisponible. Sélectionnez le texte pour le copier.";
      } finally { copy.disabled = false; }
    });
    tools.append(copy, feedback);
    article.append(label, body, state, tools);
    zone.append(article);
    return { article, body, state };
  }
  async function loadConversation(id) {
    const token = ++loading;
    fetching = true;
    selected = id || null;
    el("titre-chat").textContent = "Nouveau chat";
    navigation.select(selected);
    streams.clear();
    contents.clear();
    zone.replaceChildren();
    el("conversations").value = selected || "";
    el("modeles").disabled = Boolean(selected);
    el("dossiers").disabled = Boolean(selected);
    el("ephemere").disabled = Boolean(selected);
    const filesLoaded = files.load(selected).catch(report);
    try {
      if (selected) {
        const c = await api(`/conversations/${selected}`);
        if (token !== loading) return;
        el("titre-chat").textContent = c.titre;
        if (![...el("modeles").options].some((o) => o.value === c.modele)) option(el("modeles"), c.modele, c.modele);
        el("modeles").value = c.modele;
        el("dossiers").value = c.dossier_id || "";
        el("ephemere").checked = c.ephemere;
        for (const m of c.messages) {
          messageNode(m);
          if (m.role === "assistant") contents.set(m.id, { chunks: [m.contenu], length: [...m.contenu].length });
        }
        cards.render(zone, c.actions || []);
      }
      const state = await api("/chat/file");
      await filesLoaded;
      if (token === loading) {
        queueState(state);
        zone.scrollTop = zone.scrollHeight;
      }
    } finally {
      if (token === loading) {
        fetching = false;
        const delayed = buffered;
        buffered = [];
        for (const data of delayed) delta(data);
      }
    }
  }
  async function createConversation() {
    const c = await api("/conversations", { method: "POST", body: {
      modele: el("modeles").value, dossier_id: el("dossiers").value || null, ephemere: el("ephemere").checked,
    } });
    selected = c.id;
    await refreshLists();
    await loadConversation(c.id);
  }
  listen("conversations", "change", () => loadConversation(el("conversations").value));
  listen("nouvelle-discussion", "click", async () => {
    setPanel("chat", true);
    await loadConversation(null);
    el("chat-message").focus();
  });
  el("chat-message").title = "Entrée pour envoyer ; Maj+Entrée pour passer à la ligne";
  el("chat-message").addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing || event.keyCode === 229) return;
    event.preventDefault();
    if (!event.repeat && !el("envoyer-message").disabled) el("chat-form").requestSubmit(el("envoyer-message"));
  });
  listen("chat-form", "submit", async (event) => {
    event.preventDefault();
    if (el("envoyer-message").disabled) return;
    const text = el("chat-message").value.trim();
    if (!text) return;
    el("envoyer-message").disabled = true;
    try {
      if (!selected) await createConversation();
      const convId = selected;
      const attached = files.ids();
      await api(`/conversations/${convId}/messages`, { method: "POST", body: { contenu: text, fichiers: attached } });
      if (selected === convId) files.clear(attached);
      el("chat-message").value = "";
      await refreshLists();
      if (selected === convId) await loadConversation(convId);
    } finally { el("envoyer-message").disabled = false; }
  });
  listen("stop-chat", "click", async () => {
    if (selected) {
      await api(`/conversations/${selected}/stop`, { method: "POST" });
      await loadConversation(selected);
    }
  });
  listen("renommer-discussion", "click", async () => {
    if (!selected) return;
    const title = prompt("Titre de la discussion");
    if (title?.trim()) {
      await api(`/conversations/${selected}`, { method: "PATCH", body: { titre: title.trim() } });
      await refreshLists();
    }
  });
  listen("supprimer-discussion", "click", async () => {
    if (!selected || !confirm("Supprimer cette discussion, ses messages et ses fichiers générés ?")) return;
    await api(`/conversations/${selected}`, { method: "DELETE" });
    await loadConversation(null);
    await refreshLists();
  });
  function folderDialog(folder = null) {
    editingFolder = folder?.id || null;
    el("dossier-nom").value = folder?.nom || "";
    el("dossier-prompt").value = folder?.system_prompt || "";
    el("dossier-dialog").showModal();
  }
  listen("nouveau-dossier", "click", () => folderDialog());
  listen("modifier-dossier", "click", () => {
    const folder = folders.find((f) => f.id === el("dossiers").value);
    if (folder) folderDialog(folder);
  });
  listen("fermer-dossier", "click", () => el("dossier-dialog").close());
  listen("dossier-form", "submit", async (event) => {
    event.preventDefault();
    const f = await api(editingFolder ? `/dossiers/${editingFolder}` : "/dossiers", {
      method: editingFolder ? "PUT" : "POST",
      body: { nom: el("dossier-nom").value.trim(), system_prompt: el("dossier-prompt").value },
    });
    el("dossier-dialog").close();
    await refreshLists();
    if (!selected) el("dossiers").value = f.id;
  });
  listen("supprimer-dossier", "click", async () => {
    const folderId = el("dossiers").value;
    if (!folderId || !confirm("Supprimer ce dossier ? Les discussions seront conservées sans dossier.")) return;
    await api(`/dossiers/${folderId}`, { method: "DELETE" });
    await refreshLists();
    await loadConversation(selected);
  });
  on("chat.file", (data) => {
    const previous = queue.actif;
    queueState(data);
    if (previous?.conversation_id === selected && previous.id !== data.actif?.id) {
      loadConversation(selected).catch(report);
    }
  });
  function delta(data) {
    if (data.conversation_id !== selected) return;
    if (fetching) { buffered.push(data); return; }
    const content = contents.get(data.message_id) || { chunks: [], length: 0 };
    // Les offsets Python comptent les points Unicode, pas les unités UTF-16.
    const length = content.length;
    if (data.offset > length) {
      loadConversation(selected).catch(report);
      return;
    }
    const chunk = [...data.contenu].slice(Math.max(0, length - data.offset)).join("");
    if (!chunk) return;
    let stream = streams.get(data.message_id);
    if (!stream) {
      let article = zone.querySelector(`[data-message-id="${data.message_id}"]`);
      if (!article) article = messageNode({ id: data.message_id, role: "assistant", contenu: "", statut: "actif" }).article;
      const body = article.querySelector(".message-content");
      body.replaceChildren();
      stream = new MarkdownStream(body);
      const previous = content.chunks.join("");
      if (previous) stream.append(previous);
      streams.set(data.message_id, stream);
    }
    stream.append(chunk);
    content.chunks.push(chunk);
    content.length += [...chunk].length;
    contents.set(data.message_id, content);
    zone.scrollTop = zone.scrollHeight;
  }
  on("chat.delta", delta);
  on("chat.fin", async (data) => {
    if (data.conversation_id !== selected) return;
    streams.get(data.message_id)?.finish();
    streams.delete(data.message_id);
    try { await loadConversation(selected); } catch (error) { report(error); }
  });
  on("chat.avertissement", (data) => { if (data.conversation_id === selected) status.textContent = data.erreur; });
  on("actions.maj", (data) => { if (data.conversation_id === selected) loadConversation(selected).catch(report); });
  async function refreshModels() {
    const button = el("actualiser-modeles");
    button.disabled = true;
    try {
      const models = await api("/modeles");
      const previous = el("modeles").value;
      el("modeles").replaceChildren();
      for (const m of models.modeles) option(el("modeles"), m.name, m.name);
      const preferred = selected ? previous : models.defaut;
      if (![...el("modeles").options].some((o) => o.value === preferred)) option(el("modeles"), preferred, preferred);
      el("modeles").value = preferred;
      el("modeles-statut").textContent = models.modeles.length
        ? "Modèles actualisés. Le choix s’applique aux nouvelles discussions."
        : "Aucun modèle installé : ouvrez Ollama pour en installer un, puis actualisez cette liste.";
    } catch (error) {
      el("modeles-statut").textContent = `${error.message} Le service démarre automatiquement avec VertIA ; consultez son état dans la barre du haut. Les adresses se règlent dans Accueil et réglages.`;
    } finally { button.disabled = false; }
  }
  listen("actualiser-modeles", "click", refreshModels);
  await refreshLists();
  await refreshModels();
  queueState(queue);
  return { refreshModels, reconnect: async () => { await refreshLists(); await loadConversation(selected); } };
}

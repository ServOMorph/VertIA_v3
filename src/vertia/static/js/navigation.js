import { api } from "./api.js";
import { setPanel } from "./panels.js";

export function createNavigation({ open, editFolder, refresh, report }) {
  const tree = document.getElementById("navigation-arbre");
  const navigation = tree.closest(".navigation");
  const newProject = document.getElementById("nouveau-dossier");
  let conversations = [];
  let folders = [];
  let selected = null;
  let dragged = null;
  let pending = false;
  const expanded = new Map();
  const showAll = new Set();

  function icon(kind) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 20 20");
    svg.setAttribute("aria-hidden", "true");
    svg.classList.add("navigation-icon");
    const path = document.createElementNS(svg.namespaceURI, "path");
    path.setAttribute("d", kind === "folder"
      ? "M2.5 5.5h5l1.7 2h8.3v7.8a1.2 1.2 0 0 1-1.2 1.2H3.7a1.2 1.2 0 0 1-1.2-1.2z M2.5 10h15"
      : "M16.7 9.5a6.7 6.7 0 0 1-6.7 6.7 7.4 7.4 0 0 1-2.5-.5l-4 1 1-3.7a6.7 6.7 0 1 1 12.2-3.5z");
    svg.append(path);
    return svg;
  }

  function section(label, className) {
    const node = document.createElement("section");
    node.className = className;
    const title = document.createElement("h3");
    title.textContent = label;
    node.append(title);
    return node;
  }

  function button(label, handler, className = "navigation-action", doubleHandler = null) {
    const node = document.createElement("button");
    node.type = "button";
    node.className = className;
    node.textContent = label;
    let clickTimer;
    async function run(action) {
      if (pending) return;
      pending = true;
      try { await action(); } catch (error) { report(error); }
      finally { pending = false; }
    }
    node.addEventListener("click", (event) => {
      event.stopPropagation();
      if (doubleHandler) {
        clearTimeout(clickTimer);
        clickTimer = setTimeout(() => run(handler), 220);
      } else run(handler);
    });
    if (doubleHandler) node.addEventListener("dblclick", (event) => {
      event.preventDefault();
      event.stopPropagation();
      clearTimeout(clickTimer);
      run(doubleHandler);
    });
    return node;
  }

  const pinned = (item) => Boolean(item.epingle);
  function ordered(items) {
    return [...items].sort((a, b) => Number(pinned(b)) - Number(pinned(a)) || (a.position || 0) - (b.position || 0));
  }
  async function change(kind, item, fields) {
    await api(`/${kind}/${item.id}`, { method: "PATCH", body: fields });
    await refresh();
  }
  async function arrange(kind, source, target, after = false) {
    if (source.id === target.id) return;
    if (pinned(source) !== pinned(target)) throw Error("Réorganisez les éléments dans le même groupe d’épinglage.");
    const items = ordered(kind === "dossiers" ? folders : conversations).filter((item) => item.id !== source.id);
    items.splice(items.findIndex((item) => item.id === target.id) + Number(after), 0, source);
    await api("/navigation/ordre", { method: "PUT", body: { type: kind, ids: items.map((item) => item.id) } });
    await refresh();
  }
  function arrows(menu, kind, item, siblings) {
    const group = ordered(siblings).filter((other) => pinned(other) === pinned(item));
    const index = group.findIndex((other) => other.id === item.id);
    const up = button("Monter", () => arrange(kind, item, group[index - 1]));
    const down = button("Descendre", () => arrange(kind, item, group[index + 1], true));
    up.disabled = index <= 0;
    down.disabled = index === group.length - 1;
    menu.append(up, down);
  }
  function draggable(node, kind, item) {
    node.draggable = true;
    node.addEventListener("dragstart", (event) => {
      event.stopPropagation();
      dragged = { kind, item };
      navigation.dataset.dragging = "true";
      event.dataTransfer.setData("application/x-vertia-navigation", item.id);
      event.dataTransfer.effectAllowed = "move";
    });
    node.addEventListener("dragend", () => { dragged = null; delete navigation.dataset.dragging; });
  }
  function dropZone(node, handler) {
    node.addEventListener("dragover", (event) => {
      if (!dragged) return;
      event.preventDefault();
      event.stopPropagation();
      event.dataTransfer.dropEffect = "move";
    });
    node.addEventListener("drop", async (event) => {
      if (!dragged) return;
      event.preventDefault();
      event.stopPropagation();
      const source = dragged;
      dragged = null;
      delete navigation.dataset.dragging;
      if (pending) return;
      pending = true;
      try { await handler(source); } catch (error) { report(error); }
      finally { pending = false; }
    });
  }
  function menuFor(row, label) {
    const details = document.createElement("details");
    details.className = "navigation-menu";
    const summary = document.createElement("summary");
    summary.textContent = "…";
    summary.setAttribute("aria-label", `Actions : ${label}`);
    details.append(summary);
    const menu = document.createElement("div");
    details.append(menu);
    row.append(details);
    return menu;
  }
  function conversationNode(item, siblings) {
    const row = document.createElement("div");
    row.className = "navigation-row";
    row.dataset.conversationId = item.id;
    row.dataset.pinned = String(pinned(item));
    const rename = async () => {
      const title = prompt("Titre de la discussion", item.titre);
      if (title?.trim()) await change("conversations", item, { titre: title.trim() });
    };
    const title = button(`${item.ephemere ? "[Éphémère] " : ""}${item.titre}`, async () => {
      setPanel("chat", true);
      await open(item.id);
    }, "navigation-title", rename);
    title.title = `${item.titre} · Double-clic pour renommer`;
    title.prepend(icon("conversation"));
    if (selected === item.id) title.setAttribute("aria-current", "page");
    row.append(title);
    const menu = menuFor(row, item.titre);
    menu.append(button(pinned(item) ? "Désépingler" : "Épingler", () => change("conversations", item, { epingle: !pinned(item) })));
    menu.append(button("Renommer", rename));
    const move = document.createElement("select");
    move.setAttribute("aria-label", `Déplacer ${item.titre}`);
    move.add(new Option("Sans dossier", ""));
    for (const folder of folders) move.add(new Option(folder.nom, folder.id));
    move.value = item.dossier_id || "";
    move.addEventListener("change", async () => {
      if (pending) return;
      pending = true;
      try { await change("conversations", item, { dossier_id: move.value || null }); }
      catch (error) { move.value = item.dossier_id || ""; report(error); }
      finally { pending = false; }
    });
    menu.append(move);
    arrows(menu, "conversations", item, siblings);
    menu.append(button("Supprimer", async () => {
      if (!confirm(`Supprimer « ${item.titre} », ses messages et ses fichiers générés ?`)) return;
      await api(`/conversations/${item.id}`, { method: "DELETE" });
      if (selected === item.id) await open(null);
      await refresh();
    }));
    draggable(row, "conversations", item);
    dropZone(row, async ({ kind, item: source }) => {
      if (kind !== "conversations" || source.id === item.id) return;
      if (pinned(source) !== pinned(item)) throw Error("Réorganisez les discussions dans le même groupe d’épinglage.");
      if ((source.dossier_id || null) !== (item.dossier_id || null)) {
        await api(`/conversations/${source.id}`, { method: "PATCH", body: { dossier_id: item.dossier_id || null } });
      }
      await arrange(kind, source, item);
    });
    return row;
  }
  function render() {
    tree.replaceChildren();
    const favorites = section("Épinglés", "navigation-section navigation-pinned");
    const projects = section("Projets", "navigation-section navigation-projects");
    const projectHeading = document.createElement("header");
    projectHeading.className = "navigation-section-heading";
    projectHeading.append(projects.querySelector("h3"), newProject);
    projects.append(projectHeading);
    const root = section("Discussions", "navigation-section navigation-root");
    const heading = root.querySelector("h3");
    heading.title = "Sans dossier : déposez une discussion ici pour la sortir d’un projet";
    dropZone(heading, async ({ kind, item }) => {
      if (kind === "conversations") await change(kind, item, { dossier_id: null });
    });
    const favoriteConversations = conversations.filter(pinned);
    for (const item of ordered(favoriteConversations)) favorites.append(conversationNode(item, favoriteConversations));
    const loose = conversations.filter((item) => !item.dossier_id && !pinned(item));
    for (const item of ordered(loose)) root.append(conversationNode(item, loose));
    for (const folder of ordered(folders)) {
      const details = document.createElement("details");
      details.className = "navigation-folder";
      details.dataset.folderId = folder.id;
      details.dataset.pinned = String(pinned(folder));
      const children = conversations.filter((item) => item.dossier_id === folder.id && !pinned(item));
      details.open = expanded.get(folder.id) ?? children.some((item) => item.id === selected);
      details.addEventListener("toggle", () => expanded.set(folder.id, details.open));
      const summary = document.createElement("summary");
      const label = document.createElement("span");
      label.textContent = folder.nom;
      label.title = "Double-clic pour renommer";
      label.addEventListener("dblclick", (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (!pending) editFolder(folder);
      });
      summary.append(icon("folder"), label);
      draggable(summary, "dossiers", folder);
      dropZone(summary, async ({ kind, item }) => {
        if (kind === "dossiers") await arrange(kind, item, folder);
        else { expanded.set(folder.id, true); await change(kind, item, { dossier_id: folder.id }); }
      });
      details.append(summary);
      const folderRow = document.createElement("div");
      folderRow.className = "navigation-row navigation-folder-actions";
      const newConversation = button("Nouvelle discussion ici", async () => {
        setPanel("chat", true);
        await open(null);
        document.getElementById("dossiers").value = folder.id;
        document.getElementById("chat-message").focus();
      });
      const menu = menuFor(folderRow, folder.nom);
      menu.append(newConversation);
      menu.append(button(pinned(folder) ? "Désépingler" : "Épingler", () => change("dossiers", folder, { epingle: !pinned(folder) })));
      menu.append(button("Renommer et instructions", () => editFolder(folder)));
      arrows(menu, "dossiers", folder, folders);
      menu.append(button("Supprimer", async () => {
        if (!confirm(`Supprimer le dossier « ${folder.nom} » ? Ses discussions seront conservées sans dossier.`)) return;
        await api(`/dossiers/${folder.id}`, { method: "DELETE" });
        await refresh();
      }));
      details.append(folderRow);
      const orderedChildren = ordered(children);
      const limit = showAll.has(folder.id) ? orderedChildren.length : 5;
      for (const item of orderedChildren.slice(0, limit)) details.append(conversationNode(item, children));
      if (orderedChildren.length > 5) {
        details.append(button(showAll.has(folder.id) ? "Afficher moins" : "Afficher plus", () => {
          if (showAll.has(folder.id)) showAll.delete(folder.id);
          else showAll.add(folder.id);
          render();
        }, "navigation-show-more"));
      }
      (pinned(folder) ? favorites : projects).append(details);
    }
    if (favorites.children.length > 1) tree.append(favorites);
    tree.append(projects, root);
  }
  return {
    update(loadedFolders, loadedConversations) {
      folders = loadedFolders;
      conversations = loadedConversations;
      render();
    },
    select(id) { selected = id; render(); },
  };
}

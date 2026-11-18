import { api } from "./api.js";
import { setPanel } from "./panels.js";

export function initAccueil() {
  const home = document.getElementById("ouvrir-accueil");
  function discussion() {
    document.body.dataset.vue = "discussion";
    home.setAttribute("aria-pressed", "false");
    setPanel("chat", true);
  }
  home.addEventListener("click", () => {
    document.body.dataset.vue = "accueil";
    home.setAttribute("aria-pressed", "true");
    document.getElementById("accueil-titre").focus();
  });
  document.getElementById("accueil-discussion").addEventListener("click", discussion);
  document.getElementById("installation-fermer").addEventListener("click", discussion, true);
  document.getElementById("panel-toggles").addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-toggle]");
    if (!toggle || document.body.dataset.vue !== "accueil") return;
    discussion();
    setPanel(toggle.dataset.toggle, true);
    event.stopImmediatePropagation();
  }, true);

  const grid = document.getElementById("accueil-activites");
  const status = document.getElementById("accueil-statut");
  function tile(tag, title, detail) {
    const node = document.createElement(tag);
    node.className = "accueil-tuile";
    const label = document.createElement("strong");
    label.textContent = title;
    const description = document.createElement("span");
    description.textContent = detail;
    node.append(label, description);
    return node;
  }
  api("/v1/modules", { timeout: 5000 }).then((data) => {
    for (const activity of data.activites) {
      const section = document.createElement("section");
      section.className = "accueil-activite";
      section.dataset.activite = activity.activite;
      const heading = document.createElement("h2");
      heading.textContent = activity.titre;
      section.append(heading);
      if (activity.activite === "chat") {
        const button = tile("button", "Discussion", "Retrouver les discussions et projets");
        button.type = "button";
        button.addEventListener("click", discussion);
        section.append(button);
        grid.append(section);
        continue;
      }
      for (const module of activity.modules) {
        let href;
        try {
          const url = new URL(module.lien, location.href);
          if (["http:", "https:"].includes(url.protocol)) href = url.href;
        } catch { /* Un module sans lien reste informatif. */ }
        const health = module.sante;
        const node = tile(href ? "a" : "article", module.titre,
          `Version ${module.version} · ${health.pret ? "Prêt" : "Indisponible"}${health.message || health.erreur ? ` · ${health.message || health.erreur}` : ""}`);
        if (href) {
          node.href = href;
          if (module.nom !== "atelier") {
            node.target = "_blank";
            node.rel = "noopener noreferrer";
            node.setAttribute("aria-label", `${module.titre} (nouvel onglet)`);
          }
        } else node.tabIndex = 0;
        section.append(node);
      }
      if (!activity.modules.length && activity.activite !== "chat") {
        const node = tile("button", activity.titre, "à venir");
        node.type = "button";
        node.setAttribute("aria-disabled", "true");
        section.append(node);
      }
      grid.append(section);
    }
    const errors = document.getElementById("accueil-erreurs");
    for (const error of data.erreurs) {
      const item = document.createElement("li");
      item.textContent = error;
      errors.append(item);
    }
    status.textContent = "";
  }).catch((error) => {
    status.textContent = `Activités indisponibles : ${error.message}`;
  });
}

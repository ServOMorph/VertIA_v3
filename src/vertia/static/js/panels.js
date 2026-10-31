import { api } from "./api.js";
import { on } from "./events.js";

const STORAGE_KEY = "vertia.panels";
let state = {};

function apply() {
  for (const panel of document.querySelectorAll("[data-panel]")) {
    panel.hidden = !state[panel.dataset.panel];
  }
  for (const button of document.querySelectorAll("[data-toggle]")) {
    button.setAttribute("aria-pressed", String(Boolean(state[button.dataset.toggle])));
  }
}

async function save() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  try {
    await api("/preferences/ui", { method: "PUT", body: { panels: state } });
  } catch (error) {
    console.warn("Préférences non enregistrées", error);
  }
}

export function setPanel(name, visible) {
  if (!(name in state) || state[name] === visible) return;
  state = { ...state, [name]: visible };
  apply();
  save();
}

export async function initPanels() {
  const cached = localStorage.getItem(STORAGE_KEY);
  state = cached ? JSON.parse(cached) : {};
  apply();
  try {
    state = (await api("/preferences/ui")).panels;
    apply();
  } catch (error) {
    console.warn("Préférences indisponibles", error);
  }

  document.getElementById("panel-toggles").addEventListener("click", (event) => {
    const button = event.target.closest("[data-toggle]");
    if (button) setPanel(button.dataset.toggle, !state[button.dataset.toggle]);
  });
  document.getElementById("workspace").addEventListener("click", (event) => {
    const button = event.target.closest("[data-close]");
    if (button) setPanel(button.dataset.close, false);
  });
  on("preferences.ui", (data) => {
    state = data.panels;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    apply();
  });
}

import { connect } from "./events.js";
import { initPanels } from "./panels.js";

function setServerState(ok) {
  const badge = document.getElementById("etat-serveur");
  badge.dataset.etat = ok ? "ok" : "ko";
  badge.textContent = ok ? "en ligne" : "hors ligne";
}

async function main() {
  await initPanels();
  connect({ onOpen: () => setServerState(true), onError: () => setServerState(false) });
}

main();

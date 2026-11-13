import { connect } from "./events.js";
import { initPanels } from "./panels.js";
import { initChat } from "./chat.js";
import { initResources } from "./resources.js";
import { initTools } from "./actions.js";

import { initSetup } from "./setup.js";
import { initOllama } from "./ollama.js";

function setServerState(ok) {
  const badge = document.getElementById("etat-serveur");
  badge.dataset.etat = ok ? "ok" : "ko";
  badge.textContent = ok ? "en ligne" : "hors ligne";
}

async function main() {
  let chat;
  const ollama = initOllama(() => chat?.refreshModels());
  ollama.reconnect();
  await initSetup();
  await initPanels();
  chat = await initChat();
  const resources = await initResources();
  await initTools();
  connect({
    onOpen: () => {
      setServerState(true);
      ollama.reconnect();
      chat.reconnect().catch((error) => console.warn("Discussion indisponible", error));
      resources.reconnect();
    },
    onError: () => { setServerState(false); ollama.disconnected(); },
  });
}

main();

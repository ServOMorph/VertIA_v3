const { chromium } = require(process.env.VERTIA_PLAYWRIGHT_MODULE || "@playwright/test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const output = path.join(root, ".tmp_ui");
fs.mkdirSync(output, { recursive: true });

async function main() {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, acceptDownloads: true });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "clipboard", { value: {
        writeText: async (text) => { window.testClipboard = text; },
      } });
      window.EventSource = class {
        constructor() {
          this.handlers = {};
          window.testEvents = this;
          setTimeout(() => this.onopen?.(), 0);
        }
        addEventListener(type, handler) { this.handlers[type] = handler; }
        emit(type, data) { this.handlers[type]?.({ type, data: JSON.stringify(data) }); }
      };
    });
    let folders = [];
    let conversations = [];
    let jobs = [];
    let active = null;
    let messageId = 0;
    let resourceJobs = [];
    const resourceState = { ram: { used_mb: 12000, total_mb: 48000, percent: 25 }, gpus: [{ used_mb: 2000, total_mb: 8000, percent: 25 }], models: [{ name: "fake" }], engines: ["ollama"], warnings: [] };
    const releases = [];
    let generatedFiles = [];
    const sentAttachments = [];
    let welcomeDone = false;
    let finishPaused = true;
    let finishRoute = null;
    let setupPending = false;
    let modelsOffline = true;
    let ollamaState = { etat: 'demarrage', message: 'Ollama : démarrage automatique en cours…', modeles_charges: null, revision: 0 };
    let setupConfig = { ollama_url: "http://127.0.0.1:11434", default_model: "fake", comfy_dir: "D:/Engines/ComfyUI", comfy_port: 8189, acestep_dir: "D:/Engines/ACE", acestep_port: 8001 };
    await page.route("http://vertia.test/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const apiPath = url.pathname.replace(/^\/api/, "");
      const method = request.method();
      const body = request.postDataJSON();
      let data = {};
      if (url.pathname.startsWith("/api")) {
        if (apiPath === '/ollama/etat') data = ollamaState;
        else if (apiPath === '/v1/modules') data = { activites: [{ activite: 'chat', titre: 'Discussion', modules: [] }], erreurs: [] };
        else if (apiPath === "/installation" && method === "GET") data = { configuration: setupConfig, accueil_termine: welcomeDone, redemarrage_requis: setupPending };
        else if (apiPath === "/installation" && method === "PUT") { setupConfig = body; setupPending = true; data = { redemarrage_requis: true }; }
        else if (apiPath === "/installation/terminer") {
          if (finishPaused) { finishRoute = route; return; }
          welcomeDone = true; data = { statut: "ok" };
        }
        else if (apiPath === "/installation/diagnostic") data = {
          ollama: { joignable: true, modeles: ["fake", "<img onerror=alert(1)>"], modele_choisi_present: true },
          comfy: { joignable: false, installation: { present: true }, image: { present: false, manquants: ["models/<img onerror=alert(1)>.gguf"] }, video: { present: true } },
          ace: { joignable: false, installation: { present: false, manquants: ["acestep/api_server.py"] }, checkpoint_present: false },
          limite: "Présence des fichiers seulement ; génération à tester.",
        };
        else if (apiPath === "/preferences/ui") data = { panels: { chat: true, fichiers: true, memoire: false, outils: false } };
        else if (apiPath === "/outils") data = [{ name: "image_qwen", description: "Créer une image depuis un texte.", engine: "comfy" }];
        else if (apiPath.endsWith("/fichiers")) data = generatedFiles.filter((f) => f.conversation_id === apiPath.split("/")[2]);
        else if (apiPath.startsWith("/fichiers/") && apiPath.endsWith("/contenu")) {
          const file = generatedFiles.find((f) => f.id === apiPath.split("/")[2]);
          await route.fulfill({ body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aYo0AAAAASUVORK5CYII=", "base64"), contentType: file.mime,
            headers: url.search ? { "content-disposition": `attachment; filename="${file.name}"` } : {} });
          return;
        }
        else if (apiPath.startsWith("/fichiers/") && apiPath.endsWith("/dossier")) { releases.push("dossier"); data = { statut: "ouvert" }; }
        else if (apiPath.startsWith("/actions/")) {
          data = conversations.flatMap((c) => c.actions || []).find((a) => a.id === apiPath.split("/")[2]);
          if (body?.parameters) data.parameters = body.parameters;
          if (apiPath.endsWith("/valider")) { data.status = "validee"; data.job_id = "image-job"; }
          if (apiPath.endsWith("/annuler")) data.status = "annulee";
          await route.fulfill({ json: data });
          await page.evaluate((action) => window.testEvents.emit("actions.maj", action), data);
          return;
        }
        else if (apiPath === "/ressources") data = resourceState;
        else if (apiPath === "/ressources/liberer") { releases.push(url.search); resourceState.models = []; data = { statut: "libere" }; }
        else if (apiPath === "/jobs") data = resourceJobs;
        else if (apiPath.startsWith("/jobs/")) {
          data = resourceJobs.find((j) => j.id === apiPath.split("/")[2]);
          if (method === "PATCH") data.priority = body.priority;
          else if (apiPath.endsWith("/annuler")) { data.status = "annule"; data.resumable = 1; }
          else if (apiPath.endsWith("/reprendre")) data.status = "attente";
          data.revision++;
        }
        else if (apiPath === "/modeles") {
          if (modelsOffline) { await route.fulfill({ status: 404, json: { detail: "Not Found" } }); return; }
          data = { modeles: [{ name: "fake" }], defaut: "fake" };
        }
        else if (apiPath === "/dossiers" && method === "POST") {
          data = { id: `f${folders.length}`, ...body };
          folders.push(data);
        } else if (apiPath === "/dossiers") data = folders;
        else if (apiPath.startsWith('/dossiers/')) {
          data = folders.find((f) => f.id === apiPath.split('/')[2]);
          if (method === 'DELETE') {
            folders = folders.filter((f) => f.id !== data.id);
            conversations.filter((c) => c.dossier_id === data.id).forEach((c) => { c.dossier_id = null; });
          } else Object.assign(data, body);
        }
        else if (apiPath === '/navigation/ordre') {
          const items = body.type === 'dossiers' ? folders : conversations;
          body.ids.forEach((id, position) => { items.find((item) => item.id === id).position = position; });
          data = { statut: 'ok' };
        }
        else if (apiPath === "/conversations" && method === "POST") {
          data = { id: `c${conversations.length}`, titre: "Nouvelle discussion", messages: [], ...body };
          conversations.push(data);
        } else if (apiPath === "/conversations") data = conversations;
        else if (apiPath === "/chat/file") data = { actif: active, attente: jobs };
        else if (/^\/conversations\/[^/]+$/.test(apiPath)) {
          data = conversations.find((c) => c.id === apiPath.split("/")[2]);
          if (method === 'PATCH') Object.assign(data, body);
          if (method === 'DELETE') conversations = conversations.filter((c) => c.id !== data.id);
        } else if (apiPath.endsWith("/messages")) {
          sentAttachments.push(body.fichiers || []);
          const conv = conversations.find((c) => c.id === apiPath.split("/")[2]);
          const user = { id: ++messageId, role: "user", contenu: body.contenu, statut: "termine" };
          const assistant = { id: ++messageId, role: "assistant", contenu: "", statut: "actif" };
          conv.messages.push(user, assistant);
          conv.titre = body.contenu.slice(0, 40);
          data = { id: `j${assistant.id}`, conversation_id: conv.id, user_id: user.id, message_id: assistant.id };
          if (!active) active = data;
          else { jobs.push(data); assistant.statut = "attente"; }
        } else if (apiPath.endsWith("/stop")) {
          const conv = conversations.find((c) => c.id === apiPath.split("/")[2]);
          for (const m of conv.messages) if (["actif", "attente"].includes(m.statut)) m.statut = "arrete";
          active = null;
          jobs = [];
          data = { statut: "arrete" };
        } else throw Error(`Route inattendue : ${method} ${apiPath}`);
        await route.fulfill({ json: data });
        return;
      }
      if (url.pathname === "/") {
        await route.fulfill({ contentType: "text/html", body: fs.readFileSync(path.join(root, "src/vertia/templates/index.html"), "utf8").replaceAll("{{ version }}", "test") });
        return;
      }
      const file = path.join(root, "src/vertia", url.pathname);
      const types = { ".js": "text/javascript", ".css": "text/css", ".woff2": "font/woff2", ".png": "image/png", ".webp": "image/webp" };
      await route.fulfill({ path: file, contentType: types[path.extname(file)] });
    });
    await page.goto("http://vertia.test/");
    await page.waitForFunction(() => document.querySelector('#etat-ollama').textContent.includes('démarrage automatique'));
    await page.locator("#installation-dialog").waitFor({ state: "visible" });
    await page.locator("#installation-diagnostic").click();
    await page.getByText("Chat : Ollama joignable.", { exact: false }).waitFor();
    assert.equal(await page.locator("#installation-resultats img").count(), 0);
    await page.locator("#installation-chemins summary").click();
    await page.locator('[name="comfy_dir"]').fill("D:/Mes moteurs/ComfyUI");
    await page.locator('#installation-form [type="submit"]').click();
    await page.waitForFunction(() => document.querySelector("#installation-statut").textContent.includes("Arrêtez puis relancez"));
    await page.screenshot({ path: path.join(output, "accueil-desktop.png"), fullPage: true });
    await page.locator("#installation-fermer").click();
    assert.equal(await page.locator('#installation-dialog').evaluate((node) => node.open), false);
    assert.equal(await page.locator('#chat-message').evaluate((node) => node === document.activeElement), true);
    assert.ok(finishRoute);
    await finishRoute.fulfill({ status: 503, json: { detail: 'Écriture indisponible' } });
    await page.getByText('Accueil fermé, mais sa mémorisation a échoué', { exact: false }).waitFor();
    finishPaused = false;
    await page.waitForFunction(() => document.querySelector("#modeles-statut").textContent.includes("Le serveur VertIA ne connaît pas cette API"));
    modelsOffline = false;
    ollamaState = { etat: 'pret', message: 'Ollama disponible', modeles_charges: [], revision: 1 };
    await page.evaluate((state) => window.testEvents.emit('ollama.etat', state), ollamaState);
    await page.waitForFunction(() => document.querySelector("#modeles-statut").textContent.includes("Modèles actualisés"));
    assert.ok((await page.locator('#etat-ollama').textContent()).includes('aucun modèle chargé'));
    await page.evaluate(() => window.testEvents.emit('ollama.etat', {
      etat: 'pret', message: 'Ollama disponible', modeles_charges: [], revision: 2,
      prechargement: { etat: 'chargement', modele: 'fake', message: 'fake : chargement en cours…' },
    }));
    await page.waitForFunction(() => document.querySelector('#etat-ollama').textContent.includes('fake : chargement en cours'));
    assert.equal(await page.locator('#etat-ollama').getAttribute('data-etat'), 'attente');
    ollamaState = { ...ollamaState, modeles_charges: ['fake'], revision: 3 };
    await page.evaluate((state) => window.testEvents.emit('ollama.etat', state), ollamaState);
    await page.waitForFunction(() => document.querySelector('#etat-ollama').textContent.includes('chargé : fake'));
    await page.evaluate(() => window.testEvents.emit('ollama.etat', { etat: 'erreur', message: 'Ancien état', revision: 0 }));
    assert.ok((await page.locator('#etat-ollama').textContent()).includes('chargé : fake'));
    assert.equal(await page.locator("#modeles").inputValue(), "fake");
    await page.getByRole("button", { name: "Créer un dossier", exact: true }).click();
    await page.locator("#dossier-nom").fill("Rédaction");
    await page.locator("#dossier-prompt").fill("Réponds avec précision.");
    await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
    await page.locator("#ephemere").check();
    await page.locator("#chat-message").fill("Bonjour local");
    await page.locator("#envoyer-message").click();
    await page.waitForFunction(() => document.querySelectorAll(".message").length === 2);
    assert.equal(conversations[0].ephemere, true);
    assert.equal(conversations[0].dossier_id, folders[0].id);
    assert.equal(await page.locator("#modeles").isDisabled(), true);
    const chunks = ["Bonjour 😀\n\n", "```livrable\n", "Texte final\n", "```\n\n", '<img src="https://invalid.test/x" onerror="window.hacked=true"><script>window.hacked=true</script>'];
    let offset = 0;
    for (const chunk of chunks) {
      const data = { ...active, contenu: chunk, offset };
      conversations[0].messages[1].contenu += chunk;
      await page.evaluate((data) => window.testEvents.emit("chat.delta", data), data);
      offset += [...chunk].length;
    }
    // Le même delta reçu après un instantané ne doit pas être affiché deux fois.
    await page.evaluate((data) => window.testEvents.emit("chat.delta", data), { ...active, contenu: chunks[0], offset: 0 });
    assert.equal((await page.locator(".message--assistant").innerText()).match(/Bonjour/g).length, 1);
    await page.locator("#chat-message").fill("Question suivante");
    await page.locator("#envoyer-message").click();
    await page.waitForFunction(() => document.querySelectorAll(".message").length === 4);
    assert.equal(jobs.length, 1);
    await page.getByRole("button", { name: "Stop et annuler la file", exact: true }).click();
    await page.waitForFunction(() => [...document.querySelectorAll(".message-status")].some((e) => e.textContent === "Arrêté"));
    await page.getByRole("button", { name: "Copier", exact: true }).click();
    assert.equal(await page.evaluate(() => window.testClipboard), "Texte final\n");
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Télécharger", exact: true }).click();
    const download = await downloadPromise;
    const downloadPath = path.join(output, "livrable.txt");
    await download.saveAs(downloadPath);
    assert.equal(fs.readFileSync(downloadPath, "utf8"), "Texte final\n");
    assert.equal(await page.locator(".message--assistant img, .message--assistant script").count(), 0);
    assert.equal(await page.evaluate(() => Boolean(window.hacked)), false);
    await page.locator('[data-toggle="memoire"]').click();
    await page.locator('#memoire-zone meter').first().waitFor();
    assert.equal(await page.locator('#memoire-zone meter').count(), 2);
    await page.getByRole("button", { name: "Décharger fake", exact: true }).click();
    await page.waitForFunction(() => document.querySelector('#memoire-zone').textContent.includes("Aucun modèle chargé connu"));
    assert.ok(releases[0].includes("modele=fake"));
    resourceJobs = [{ id: "resource-job", kind: "image <script>", engine: "comfy", status: "attente", progress: 0, priority: 0, resumable: 1, revision: 0 }];
    await page.evaluate((job) => window.testEvents.emit("jobs.maj", job), resourceJobs[0]);
    const jobNode = page.locator('[data-job-id="resource-job"]');
    await jobNode.locator('input').fill("10");
    await jobNode.getByRole("button", { name: "Appliquer" }).click();
    await page.waitForFunction(() => document.querySelector('[data-job-id="resource-job"] input')?.value === "10");
    assert.equal(resourceJobs[0].priority, 10);
    await jobNode.getByRole("button", { name: "Annuler", exact: true }).click();
    await jobNode.getByRole("button", { name: "Relancer", exact: true }).waitFor();
    assert.equal(await jobNode.locator('script').count(), 0);
    resourceJobs[0] = { ...resourceJobs[0], status: "actif", progress: 75, revision: 3 };
    await page.evaluate((job) => window.testEvents.emit("jobs.maj", job), resourceJobs[0]);
    await page.waitForFunction(() => document.querySelector('[data-job-id="resource-job"]').textContent.includes('75 %'));
    await page.evaluate(() => window.testEvents.emit("ressources.erreur", { erreur: "Mesure indisponible simulée" }));
    assert.ok((await page.locator('#memoire-zone [role="status"]').innerText()).includes("Mesure indisponible"));
    const action = { id: "a1", conversation_id: conversations[0].id, message_id: conversations[0].messages[1].id, tool: "image_qwen", status: "proposee", parameters: { prompt: '<script>window.hacked=true</script> un chat', negatif: "", largeur: 1024, hauteur: 1024, etapes: 25, seed: 0, mode: "t2i", references: [], masque: null }, result: {} };
    conversations[0].actions = [action];
    await page.evaluate((action) => window.testEvents.emit("actions.maj", action), action);
    const card = page.locator('[data-action-id="a1"]');
    await card.locator('[name="prompt"]').waitFor();
    assert.equal(await card.locator('script').count(), 0);
    await card.locator('[name="prompt"]').fill("Un chat sous les étoiles");
    await card.locator('[name="largeur"]').fill("768");
    await card.getByRole("button", { name: "Enregistrer les modifications" }).click();
    await page.waitForFunction(() => document.querySelector('[data-action-id="a1"] [name="largeur"]')?.value === "768");
    assert.equal(action.parameters.prompt, "Un chat sous les étoiles");
    await card.getByRole("button", { name: "Lancer la génération" }).click();
    await page.waitForFunction(() => document.querySelector('[data-action-id="a1"] [name="prompt"]')?.disabled);
    assert.equal(action.status, "validee");
    await page.evaluate(() => window.testEvents.emit("jobs.maj", { id: "image-job", kind: "outil", engine: "comfy", priority: 0, resumable: 1, payload: { action_id: "a1" }, status: "actif", progress: 60, revision: 0 }));
    assert.ok((await card.locator('.action-status').innerText()).includes("60 %"));
    const cancelled = { ...action, id: "a2", status: "proposee", job_id: null };
    conversations[0].actions.push(cancelled);
    await page.evaluate((action) => window.testEvents.emit("actions.maj", action), cancelled);
    const secondCard = page.locator('[data-action-id="a2"]');
    await secondCard.getByRole("button", { name: "Annuler la carte" }).click();
    await secondCard.getByText("Carte annulée", { exact: true }).waitFor();
    assert.equal(cancelled.status, "annulee");
    const musicAction = { id: "music-a1", conversation_id: conversations[0].id, message_id: conversations[0].messages[1].id,
      tool: "musique_ace", status: "proposee", parameters: { prompt: "Compose une chanson", titre: '<script>window.hacked=true</script>',
        caption: "folk, female vocals, guitar, drums, warm production, peaceful", paroles: "[verse]\nLa mer\n\n[chorus]\nLe vent", bpm: 100, duree: 60, instrumental: false, langue: "fr", seed: 0 }, result: {} };
    conversations[0].actions.push(musicAction);
    await page.evaluate((action) => window.testEvents.emit("actions.maj", action), musicAction);
    const musicCard = page.locator('[data-action-id="music-a1"]');
    await musicCard.getByText("Composer une musique", { exact: true }).waitFor();
    assert.equal(await musicCard.locator('[name="largeur"], [name="etapes"], script').count(), 0);
    await musicCard.locator('[name="titre"]').fill("Le rivage");
    await musicCard.locator('[name="duree"]').fill("90");
    await musicCard.locator('[name="langue"]').selectOption("en");
    await musicCard.locator('[name="instrumental"]').check();
    await musicCard.locator('[name="paroles"]').fill("");
    await musicCard.locator('[name="caption"]').fill("ambient, instrumental, piano, drums, warm production, peaceful");
    await musicCard.getByRole("button", { name: "Enregistrer les modifications" }).click();
    await page.waitForFunction(() => document.querySelector('[data-action-id="music-a1"] [name="titre"]')?.value === "Le rivage");
    assert.equal(musicAction.parameters.instrumental, true);
    assert.equal(musicAction.parameters.duree, 90);
    assert.equal(musicAction.parameters.langue, "en");
    assert.equal(musicAction.parameters.paroles, "");
    await musicCard.getByRole("button", { name: "Lancer la génération" }).click();
    await page.waitForFunction(() => document.querySelector('[data-action-id="music-a1"] [name="caption"]')?.disabled);
    generatedFiles = ["image", "audio", "video"].map((type, index) => ({ id: `file-${type}`, conversation_id: conversations[0].id, type,
      mime: ["image/png", "audio/mpeg", "video/mp4"][index], name: ["image.png", "musique.mp3", "video.mp4"][index], size: 1024,
      prompt: '<script>window.hacked=true</script> Un chat sous les étoiles' }));
    await page.evaluate((conversation_id) => window.testEvents.emit("fichiers.maj", { conversation_id }), conversations[0].id);
    await page.locator('.file-card').first().waitFor();
    assert.equal(await page.locator('.file-card').count(), 3);
    assert.equal(await page.locator('.file-card img, .file-card audio, .file-card video').count(), 3);
    assert.equal(await page.locator('.file-card script').count(), 0);
    musicAction.result = { audios: ["result.mp3"], files: ["file-audio"] };
    await page.evaluate((action) => window.testEvents.emit("actions.maj", action), musicAction);
    await musicCard.locator('audio').waitFor();
    assert.ok((await musicCard.locator('audio').getAttribute('src')).endsWith('/file-audio/contenu'));
    const videoAction = { id: "video-a1", conversation_id: conversations[0].id, message_id: conversations[0].messages[1].id,
      tool: "video_wan", status: "proposee", parameters: { prompt: '<script>window.hacked=true</script> La mer', negatif: "",
        largeur: 640, hauteur: 384, images: 49, etapes: 20, seed: 0, mode: "i2v", references: ["file-image"] }, result: {} };
    conversations[0].actions.push(videoAction);
    await page.evaluate((action) => window.testEvents.emit("actions.maj", action), videoAction);
    const videoCard = page.locator('[data-action-id="video-a1"]');
    await videoCard.getByText("Animer une image", { exact: true }).waitFor();
    assert.equal(await videoCard.locator('script, [name="duree"], [name="paroles"]').count(), 0);
    assert.equal(await videoCard.locator('[name="largeur"]').isEnabled(), true);
    await videoCard.locator('[name="prompt"]').fill("La mer et les vagues en mouvement");
    await videoCard.locator('[name="images"]').fill("50");
    await videoCard.getByRole("button", { name: "Lancer la génération" }).click();
    assert.equal(videoAction.status, "proposee");
    await videoCard.locator('[name="images"]').fill("53");
    await videoCard.getByRole("button", { name: "Enregistrer les modifications" }).click();
    await page.waitForFunction(() => document.querySelector('[data-action-id="video-a1"] [name="images"]')?.value === "53");
    assert.equal(videoAction.parameters.images, 53);
    assert.deepEqual(videoAction.parameters.references, ["file-image"]);
    await videoCard.getByRole("button", { name: "Lancer la génération" }).click();
    await page.waitForFunction(() => document.querySelector('[data-action-id="video-a1"] [name="prompt"]')?.disabled);
    videoAction.result = { videos: [{ filename: "video.mp4", type: "output", subfolder: "" }], files: ["file-video"] };
    await page.evaluate((action) => window.testEvents.emit("actions.maj", action), videoAction);
    await videoCard.locator('video').waitFor();
    assert.ok((await videoCard.locator('video').getAttribute('src')).endsWith('/file-video/contenu'));
    const imageFile = page.locator('[data-file-id="file-image"]');
    await imageFile.getByRole("button", { name: "Utiliser dans le chat" }).click();
    await page.locator('#chat-form').dispatchEvent('drop', {
      dataTransfer: await page.evaluateHandle(() => { const data = new DataTransfer(); data.setData('application/x-vertia-file', 'file-audio'); return data; }),
    });
    assert.equal(await page.locator('.file-attachment').count(), 2);
    await page.locator('.file-attachment').filter({ hasText: 'audio' }).getByRole('button', { name: 'Retirer' }).click();
    assert.equal(await page.locator('.file-attachment').count(), 1);
    await page.locator('#chat-message').fill('Modifie cette image');
    await page.locator('#envoyer-message').click();
    await page.waitForFunction(() => document.querySelectorAll('.file-attachment').length === 0);
    assert.deepEqual(sentAttachments.at(-1), ['file-image']);
    await page.getByRole('button', { name: 'Stop et annuler la file', exact: true }).click();
    const imageDownloadPromise = page.waitForEvent('download');
    await imageFile.getByRole('link', { name: 'Télécharger', exact: true }).click();
    const imageDownload = await imageDownloadPromise;
    assert.equal(imageDownload.suggestedFilename(), 'image.png');
    assert.ok(imageDownload.url().endsWith('/file-image/contenu?telecharger=true'));
    // Edge annule les réponses HTTP interceptées en téléchargement ; octets et en-têtes sont testés côté API.
    const downloadFailure = await imageDownload.failure();
    assert.ok(downloadFailure === null || downloadFailure === 'canceled');
    const folderResponse = page.waitForResponse((response) => response.url().endsWith('/file-image/dossier'));
    await imageFile.getByRole('button', { name: 'Ouvrir le dossier', exact: true }).click();
    await folderResponse;
    assert.ok(releases.includes('dossier'));
    assert.equal(await page.evaluate(() => Boolean(window.hacked)), false);
    await card.evaluate((node) => node.scrollIntoView({ block: "start" }));
    await page.screenshot({ path: path.join(output, "actions-desktop.png"), fullPage: true });
    await page.screenshot({ path: path.join(output, "chat-desktop.png"), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await videoCard.evaluate((node) => node.scrollIntoView({ block: "start" }));
    await page.screenshot({ path: path.join(output, "video-mobile.png"), fullPage: true });
    await videoCard.screenshot({ path: path.join(output, "video-carte-mobile.png") });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await musicCard.evaluate((node) => node.scrollIntoView({ block: "start" }));
    await page.screenshot({ path: path.join(output, "musique-mobile.png"), fullPage: true });
    await card.scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(output, "actions-mobile.png"), fullPage: true });
    await page.screenshot({ path: path.join(output, "chat-mobile.png"), fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.locator('[data-panel="fichiers"]').evaluate((node) => node.scrollIntoView({ block: "start" }));
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.screenshot({ path: path.join(output, "fichiers-mobile.png"), fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await imageFile.getByRole('button', { name: 'Utiliser dans le chat' }).click();
    await page.locator('#nouvelle-discussion').click();
    await page.waitForFunction(() => document.querySelectorAll('.file-attachment').length === 0);
    assert.equal(await page.locator('.file-card').count(), 0);
    await page.evaluate(() => {
      document.querySelector('[data-panel="memoire"]').scrollIntoView({ block: "start" });
      return new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    });
    await page.screenshot({ path: path.join(output, "memoire-mobile.png"), fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.evaluate(async () => {
      const { MarkdownStream } = await import("/static/js/markdown.js");
      const original = window.marked;
      let processed = 0;
      window.marked = { parse: (text) => { processed += text.length; return original.parse(text); } };
      const node = document.createElement("div");
      const stream = new MarkdownStream(node);
      for (let index = 0; index < 4000; index++) stream.append("a");
      stream.finish();
      window.marked = original;
      if (processed !== 4000 || node.textContent.trim().length !== 4000) throw Error(`Flux : ${processed} caractères parsés, ${node.textContent.trim().length} affichés`);
    });
    await page.locator("#ouvrir-installation").click();
    await page.locator("#installation-dialog").waitFor({ state: "visible" });
    assert.equal(await page.locator('[name="comfy_dir"]').inputValue(), "D:/Mes moteurs/ComfyUI");
    await page.screenshot({ path: path.join(output, "accueil-mobile.png"), fullPage: true });
    assert.equal(await page.locator("#installation-dialog").evaluate((node) => node.scrollWidth <= node.clientWidth), true);
    await page.locator("#installation-fermer").click();
    await page.setViewportSize({ width: 1440, height: 1100 });
    ollamaState = { etat: 'erreur', message: 'Ollama introuvable', modeles_charges: null, revision: 4 };
    await page.evaluate((state) => window.testEvents.emit('ollama.etat', state), ollamaState);
    await page.waitForFunction(() => document.querySelector('#etat-ollama').dataset.etat === 'ko');
    await page.evaluate(() => window.testEvents.onerror());
    assert.ok((await page.locator('#etat-ollama').textContent()).includes('état inconnu'));
    ollamaState = { ...ollamaState, revision: 0 };
    await page.evaluate(() => window.testEvents.onopen());
    await page.waitForFunction(() => document.querySelector('#etat-ollama').textContent.includes('Ollama introuvable'));
    folders.push({ id: 'nav-f1', nom: 'Projet Alpha', system_prompt: '' }, { id: 'nav-f2', nom: 'Projet Beta', system_prompt: '' });
    conversations.push(...['nav-c1', 'nav-c2'].map((id) => ({ id, titre: id, dossier_id: null, modele: 'fake', messages: [], ephemere: false })));
    await page.evaluate(() => window.testEvents.onopen());
    const folderAlpha = page.locator('[data-folder-id="nav-f1"]');
    const folderBeta = page.locator('[data-folder-id="nav-f2"]');
    const convOne = page.locator('.navigation-row[data-conversation-id="nav-c1"]');
    const convTwo = page.locator('.navigation-row[data-conversation-id="nav-c2"]');
    await folderAlpha.waitFor();
    async function navigationMenu(row) {
      const menu = row.locator(':scope > .navigation-menu');
      await menu.locator('summary').click();
      return menu;
    }
    let menu = await navigationMenu(convOne);
    await menu.getByRole('button', { name: 'Épingler', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('.navigation-pinned [data-conversation-id="nav-c1"]')?.dataset.pinned === 'true');
    assert.equal(conversations.find((c) => c.id === 'nav-c1').epingle, true);
    menu = await navigationMenu(convOne);
    await menu.getByRole('button', { name: 'Désépingler', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('[data-conversation-id="nav-c1"]')?.dataset.pinned === 'false');
    menu = await navigationMenu(convOne);
    page.once('dialog', (dialog) => dialog.accept('Discussion renommée'));
    await menu.getByRole('button', { name: 'Renommer', exact: true }).click();
    await convOne.getByRole('button', { name: 'Discussion renommée', exact: true }).waitFor();
    await convOne.getByRole('button', { name: 'Discussion renommée', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('[data-conversation-id="nav-c1"] .navigation-title').getAttribute('aria-current') === 'page');
    await convTwo.dragTo(convOne);
    await page.waitForFunction(() => document.querySelector('.navigation-root .navigation-row').dataset.conversationId === 'nav-c2');
    assert.ok(conversations.find((c) => c.id === 'nav-c2').position < conversations.find((c) => c.id === 'nav-c1').position);
    menu = await navigationMenu(convTwo);
    await menu.getByRole('button', { name: 'Descendre', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('.navigation-root .navigation-row').dataset.conversationId === 'nav-c1');
    await convTwo.dragTo(folderAlpha.locator(':scope > summary'));
    await folderAlpha.locator('[data-conversation-id="nav-c2"]').waitFor();
    assert.equal(conversations.find((c) => c.id === 'nav-c2').dossier_id, 'nav-f1');
    await folderAlpha.locator(':scope > summary').click();
    assert.equal(await convTwo.isVisible(), false);
    await folderAlpha.locator(':scope > summary').click();
    await convTwo.waitFor();
    const folderActions = folderAlpha.locator(':scope > .navigation-folder-actions');
    menu = await navigationMenu(folderActions);
    await menu.getByRole('button', { name: 'Nouvelle discussion ici' }).click();
    await page.waitForFunction(() => document.querySelector('#dossiers').value === 'nav-f1');
    assert.equal(await page.locator('#modeles').isDisabled(), false);
    menu = await navigationMenu(folderActions);
    await menu.getByRole('button', { name: 'Épingler', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('.navigation-folder').dataset.folderId === 'nav-f1');
    menu = await navigationMenu(folderActions);
    await menu.getByRole('button', { name: 'Désépingler', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('[data-folder-id="nav-f1"]')?.dataset.pinned === 'false');
    await folderBeta.locator(':scope > summary').dragTo(folderAlpha.locator(':scope > summary'));
    await page.waitForFunction(() => [...document.querySelectorAll('.navigation-folder')].findIndex((n) => n.dataset.folderId === 'nav-f2') < [...document.querySelectorAll('.navigation-folder')].findIndex((n) => n.dataset.folderId === 'nav-f1'));
    menu = await navigationMenu(folderActions);
    await menu.getByRole('button', { name: 'Renommer et instructions' }).click();
    await page.locator('#dossier-nom').fill('Projet renommé');
    await page.locator('#dossier-form [type="submit"]').click();
    await folderAlpha.locator(':scope > summary').getByText('Projet renommé', { exact: false }).waitFor();
    conversations.push(...Array.from({ length: 6 }, (_, index) => ({
      id: `nav-extra-${index}`, titre: `Préparer le livrable ${index + 1}`, dossier_id: 'nav-f2', modele: 'fake', messages: [], ephemere: false,
    })));
    await page.evaluate(() => window.testEvents.onopen());
    await page.waitForFunction(() => document.querySelector('[data-conversation-id="nav-extra-0"]'));
    await folderBeta.locator(':scope > summary').click();
    await folderBeta.getByRole('button', { name: 'Afficher plus', exact: true }).waitFor();
    assert.equal(await folderBeta.locator('[data-conversation-id]').count(), 5);
    await folderBeta.getByRole('button', { name: 'Afficher plus', exact: true }).click();
    assert.equal(await folderBeta.locator('[data-conversation-id]').count(), 6);
    await folderBeta.getByRole('button', { name: 'Afficher moins', exact: true }).click();
    menu = await navigationMenu(convOne);
    await menu.getByRole('button', { name: 'Épingler', exact: true }).click();
    await page.locator('.navigation-pinned [data-conversation-id="nav-c1"]').waitFor();
    assert.equal(await page.locator('[data-conversation-id="nav-c1"]').count(), 1);
    menu = await navigationMenu(folderActions);
    await menu.getByRole('button', { name: 'Épingler', exact: true }).click();
    await page.locator('.navigation-pinned [data-folder-id="nav-f1"]').waitFor();
    await convTwo.getByRole('button', { name: 'nav-c2', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('[data-conversation-id="nav-c2"] .navigation-title').getAttribute('aria-current') === 'page');
    await page.screenshot({ path: path.join(output, 'navigation-desktop.png'), fullPage: true });
    await page.locator('.navigation').screenshot({ path: path.join(output, 'navigation-codex.png') });
    menu = await navigationMenu(convTwo);
    await menu.getByLabel('Déplacer nav-c2').selectOption('');
    await page.locator('.navigation-root [data-conversation-id="nav-c2"]').waitFor();
    await convTwo.dragTo(folderAlpha.locator(':scope > summary'));
    await folderAlpha.locator('[data-conversation-id="nav-c2"]').waitFor();
    menu = await navigationMenu(folderActions);
    page.once('dialog', (dialog) => dialog.accept());
    await menu.getByRole('button', { name: 'Supprimer', exact: true }).click();
    await folderAlpha.waitFor({ state: 'detached' });
    await page.locator('.navigation-root [data-conversation-id="nav-c2"]').waitFor();
    menu = await navigationMenu(convOne);
    page.once('dialog', (dialog) => dialog.accept());
    await menu.getByRole('button', { name: 'Supprimer', exact: true }).click();
    await convOne.waitFor({ state: 'detached' });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(output, 'navigation-mobile.png'), fullPage: true });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    assert.deepEqual(errors, []);
    console.log("UI Navigation : épinglage, renommage, ordre, glisser-déposer, déplacement, dossiers dépliables, suppression ; accueil sans réponse réseau ; Chat, outils, fichiers et mobile : OK");
  } finally { await browser.close(); }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });

const { chromium } = require(process.env.VERTIA_PLAYWRIGHT_MODULE || "@playwright/test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..", "src", "vertia");
const activities = ["image", "musique", "voix", "video", "chat", "3d", "animation_3d", "worldmodel", "llm", "outil"];

async function main() {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.addInitScript(() => {
      window.EventSource = class { addEventListener() {} };
    });
    let unavailable = false;
    await page.route("http://vertia.test/**", async (route) => {
      const url = new URL(route.request().url());
      const name = url.pathname;
      if (name === "/api/v1/modules") {
        if (unavailable) return route.fulfill({ status: 503, json: { detail: "Registre indisponible" } });
        return route.fulfill({ json: {
          activites: activities.map((activite) => ({ activite, titre: activite, modules: activite === "image" ? [
            { nom: "atelier", titre: "Atelier", version: "0.1.0", lien: "http://127.0.0.1:4320", sante: { pret: true } },
            { nom: "info", titre: "<img src=x onerror=alert(1)>", version: "1.0.0", lien: null, sante: { pret: false, erreur: "Poids absents" } },
            { nom: "invalide", titre: "Lien invalide", version: "1.0.0", lien: "javascript:alert(1)", sante: {} },
          ] : [] })), erreurs: ["Module cassé <img src=x onerror=alert(1)>"],
        } });
      }
      if (name.startsWith("/api/")) {
        const responses = {
          "/api/installation": { accueil_termine: true, configuration: {} },
          "/api/ollama/etat": { etat: "pret", revision: 1, message: "Prêt", modeles_charges: [] },
          "/api/preferences/ui": { panels: { chat: true, fichiers: true, memoire: false, outils: false } },
          "/api/dossiers": [], "/api/conversations": [], "/api/outils": [], "/api/jobs": [],
          "/api/modeles": { modeles: [{ name: "factice" }], defaut: "factice" },
          "/api/chat/file": { actif: null, attente: [] },
          "/api/ressources": { ram: { used_mb: 100, total_mb: 1000, percent: 10 }, gpus: [] },
        };
        assert.ok(name in responses, `API inattendue : ${name}`);
        return route.fulfill({ json: responses[name] });
      }
      if (name === "/") return route.fulfill({ contentType: "text/html", body: fs.readFileSync(path.join(root, "templates/index.html"), "utf8").replaceAll("{{ version }}", "test") });
      const types = { ".js": "text/javascript", ".css": "text/css", ".woff2": "font/woff2", ".png": "image/png", ".webp": "image/webp" };
      return route.fulfill({ path: path.join(root, name), contentType: types[path.extname(name)] });
    });
    await page.goto("http://vertia.test/");
    await page.locator("#accueil-activites .accueil-activite").last().waitFor();
    await page.waitForFunction(() => document.querySelector("#modeles").value === "factice");
    assert.equal(await page.locator("#accueil").isVisible(), true);
    assert.equal(await page.locator(".app-layout").isVisible(), false);
    assert.deepEqual(await page.locator(".accueil-activite").evaluateAll((nodes) => nodes.map((n) => n.dataset.activite)), activities);
    const link = page.getByRole("link", { name: "Atelier (nouvel onglet)" });
    assert.equal(await link.getAttribute("href"), "http://127.0.0.1:4320/");
    assert.equal(await link.getAttribute("target"), "_blank");
    assert.equal(await link.getAttribute("rel"), "noopener noreferrer");
    await link.focus();
    assert.equal(await link.evaluate((node) => node === document.activeElement), true);
    assert.equal(await page.locator("#accueil img").count(), 0);
    assert.match(await page.locator("#accueil-erreurs").textContent(), /Module cassé/);
    assert.match(await page.locator("article.accueil-tuile").first().textContent(), /1.0.0.*Indisponible.*Poids absents/);
    const disabled = page.locator('[data-activite="voix"] button');
    assert.equal(await disabled.getAttribute("aria-disabled"), "true");
    await disabled.focus();
    await page.keyboard.press("Enter");
    assert.equal(await page.locator("#accueil").isVisible(), true);
    const discussion = page.locator('[data-activite="chat"] button');
    await discussion.focus();
    await page.keyboard.press("Enter");
    assert.equal(await page.locator('[data-panel="chat"]').isVisible(), true);
    await page.locator("#ouvrir-accueil").click();
    await page.locator('[data-toggle="chat"]').click();
    assert.equal(await page.locator('[data-panel="chat"]').isVisible(), true);
    await page.locator("#ouvrir-accueil").click();
    await page.locator('[data-toggle="fichiers"]').click();
    assert.equal(await page.locator('[data-panel="fichiers"]').isVisible(), true);
    await page.locator("#ouvrir-accueil").click();
    await page.locator('[data-toggle="memoire"]').click();
    assert.equal(await page.locator('[data-panel="memoire"]').isVisible(), true);
    await page.locator("#ouvrir-accueil").click();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    unavailable = true;
    await page.reload();
    await page.getByText("Activités indisponibles : Registre indisponible").waitFor();
    await page.locator("#accueil-discussion").click();
    await page.locator('[data-panel="chat"]').waitFor();
    assert.deepEqual(errors, []);
    console.log("UI Accueil : catalogue, clavier, liens, diagnostics, Discussion, panneaux, mobile et repli réseau : OK");
  } finally { await browser.close(); }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });

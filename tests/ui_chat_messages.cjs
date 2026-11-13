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
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "clipboard", { value: { writeText: async (text) => {
        if (window.copyFails) throw Error("Refus simulé");
        window.testClipboard = text;
      } } });
      window.EventSource = class {
        constructor() { this.handlers = {}; window.testEvents = this; }
        addEventListener(type, handler) { this.handlers[type] = handler; }
        emit(type, data) { this.handlers[type]?.({ type, data: JSON.stringify(data) }); }
      };
    });
    const rawUser = "Peux-tu expliquer ce code ?\n<img src=x onerror=alert(1)> 😀";
    const rawAssistant = "Voici le **code complet** :\n\n```python\nprint('Bonjour 😀')\n```\n\nLe Markdown doit rester intact à la copie.";
    const conversations = [
      { id: 'c1', titre: 'Comprendre le code', modele: 'fake', dossier_id: 'f1', actions: [], ephemere: false, messages: [
        { id: 1, role: 'user', contenu: rawUser, statut: 'termine' },
        { id: 2, role: 'assistant', contenu: rawAssistant, statut: 'termine' },
        { id: 3, role: 'user', contenu: 'Continue avec un exemple concret.', statut: 'termine' },
        { id: 4, role: 'assistant', contenu: 'Un début de réponse ', statut: 'actif' },
      ] },
      { id: 'c2', titre: 'Autre discussion', modele: 'fake', dossier_id: null, actions: [], ephemere: false, messages: [
        { id: 1, role: 'user', contenu: 'Question dans une autre discussion.', statut: 'termine' },
        { id: 2, role: 'assistant', contenu: '**Une autre réponse**, sans mélange.', statut: 'arrete' },
      ] },
    ];
    const sentMessages = [];
    await page.route('http://vertia.test/**', async (route) => {
      const url = new URL(route.request().url());
      const apiPath = url.pathname.replace(/^\/api/, '');
      if (url.pathname.startsWith('/api/')) {
        let data;
        if (apiPath === '/preferences/ui') data = { panels: { chat: true, fichiers: false, memoire: false, outils: false } };
        else if (apiPath === '/dossiers') data = [{ id: 'f1', nom: 'Développement', system_prompt: '' }];
        else if (apiPath === '/conversations') data = conversations;
        else if (apiPath === '/modeles') data = { modeles: [{ name: 'fake' }], defaut: 'fake' };
        else if (apiPath === '/chat/file') data = { actif: null, attente: [] };
        else if (apiPath.endsWith('/fichiers')) data = [];
        else if (apiPath.endsWith('/messages') && route.request().method() === 'POST') {
          const body = route.request().postDataJSON();
          sentMessages.push(body.contenu);
          const conversation = conversations.find((c) => c.id === apiPath.split('/')[2]);
          conversation.messages.push({ id: 5, role: 'user', contenu: body.contenu, statut: 'termine' },
            { id: 6, role: 'assistant', contenu: 'Réponse mobile simulée.', statut: 'termine' });
          data = { id: 'mobile-job' };
        }
        else if (/^\/conversations\/c[12]$/.test(apiPath)) data = conversations.find((c) => c.id === apiPath.split('/')[2]);
        else throw Error('Route inattendue : ' + apiPath);
        await route.fulfill({ json: data });
      } else if (url.pathname === '/') {
        const html = fs.readFileSync(path.join(root, 'src/vertia/templates/index.html'), 'utf8').replaceAll('{{ version }}', 'test');
        await route.fulfill({ body: html, contentType: 'text/html' });
      } else if (url.pathname === '/static/js/main.js') {
        await route.fulfill({ contentType: 'text/javascript', body: `
          import { initChat } from './chat.js';
          import { initPanels } from './panels.js';
          import { connect } from './events.js';
          await initPanels();
          await initChat();
          connect();
          document.getElementById('etat-serveur').textContent = 'en ligne';
          document.getElementById('etat-serveur').dataset.etat = 'ok';
          document.getElementById('etat-ollama').textContent = 'Ollama disponible · chargé : fake';
          document.getElementById('etat-ollama').dataset.etat = 'ok';
          window.testReady = true;
        ` });
      } else {
        const file = path.join(root, 'src/vertia', url.pathname);
        const types = { '.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2', '.png': 'image/png', '.webp': 'image/webp' };
        await route.fulfill({ path: file, contentType: types[path.extname(file)] });
      }
    });
    await page.goto('http://vertia.test/');
    await page.waitForFunction(() => window.testReady);
    async function open(id) {
      await page.evaluate((id) => {
        const select = document.getElementById('conversations');
        select.value = id;
        select.dispatchEvent(new Event('change'));
      }, id);
      await page.waitForFunction((title) => document.getElementById('titre-chat').textContent === title,
        conversations.find((c) => c.id === id).titre);
      await page.waitForFunction((count) => document.querySelectorAll('.message-copy').length === count,
        conversations.find((c) => c.id === id).messages.length);
    }
    async function copy(id, expected) {
      await page.locator(`[data-message-id="${id}"] .message-copy`).click();
      assert.equal(await page.evaluate(() => window.testClipboard), expected);
    }
    await open('c1');
    assert.equal(await page.locator('.message--user img').count(), 0);
    assert.equal(await page.locator('.message-copy').count(), 4);
    await copy(1, rawUser);
    await copy(2, rawAssistant);
    const appended = '**et sa suite 😀**\n\nToujours le même message.';
    await page.evaluate((data) => window.testEvents.emit('chat.delta', data), {
      conversation_id: 'c1', message_id: 4, offset: [...conversations[0].messages[3].contenu].length, contenu: appended,
    });
    const streamed = conversations[0].messages[3].contenu + appended;
    await copy(4, streamed);
    conversations[0].messages[3].contenu = streamed;
    conversations[0].messages[3].statut = 'arrete';
    await page.evaluate(() => window.testEvents.emit('chat.fin', { conversation_id: 'c1', message_id: 4 }));
    await page.waitForFunction(() => document.querySelector('[data-message-id="4"] .message-status')?.textContent === 'Arrêté');
    await copy(4, streamed);
    await open('c2');
    await copy(2, conversations[1].messages[1].contenu);
    await open('c1');
    await copy(2, rawAssistant);
    await page.evaluate(() => { window.copyFails = true; });
    await page.locator('[data-message-id="1"] .message-copy').click();
    await page.locator('[data-message-id="1"] .message-copy-status').getByText('Copie indisponible.', { exact: false }).waitFor();
    await page.evaluate(() => { window.copyFails = false; });
    await copy(1, rawUser);
    assert.equal(await page.locator('[data-message-id="1"] .message-copy-status').textContent(), 'Copié');
    await page.screenshot({ path: path.join(output, 'chat-codex-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('[data-panel="chat"]').evaluate((node) => node.scrollIntoView({ block: 'start' }));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await copy(4, streamed);
    await page.locator('#envoyer-message').scrollIntoViewIfNeeded();
    assert.equal(await page.locator('#envoyer-message').isVisible(), true);
    const compose = page.locator('#chat-message');
    await compose.fill('   ');
    await compose.press('Enter');
    assert.deepEqual(sentMessages, []);
    await compose.fill('Première ligne depuis le téléphone.');
    await compose.press('Shift+Enter');
    await compose.pressSequentially('Deuxième ligne.');
    const multiline = 'Première ligne depuis le téléphone.\nDeuxième ligne.';
    assert.equal(await compose.inputValue(), multiline);
    assert.deepEqual(sentMessages, []);
    await compose.dispatchEvent('keydown', { key: 'Enter', isComposing: true });
    await compose.dispatchEvent('keydown', { key: 'Enter', repeat: true });
    assert.deepEqual(sentMessages, []);
    await compose.press('Enter');
    await page.waitForFunction(() => document.querySelectorAll('.message').length === 6);
    assert.deepEqual(sentMessages, [multiline]);
    assert.equal(await page.locator('#chat-message').inputValue(), '');
    await page.locator('#envoyer-message').scrollIntoViewIfNeeded();
    assert.equal(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight + 1), true);
    await page.screenshot({ path: path.join(output, 'chat-codex-mobile.png'), fullPage: true });
    assert.deepEqual(errors, []);
    console.log('Chat Codex : copie user/assistant Markdown brut, flux Unicode, arrêt, rechargement, changement de discussion, refus clipboard et mobile : OK');
  } finally { await browser.close(); }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });

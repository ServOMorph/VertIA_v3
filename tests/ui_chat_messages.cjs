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
    const captures = [];
    let rejectModelChange = false;
    await page.route('http://vertia.test/**', async (route) => {
      const url = new URL(route.request().url());
      const apiPath = url.pathname.replace(/^\/api/, '');
      if (url.pathname.startsWith('/api/')) {
        let data;
        if (apiPath === '/preferences/ui') data = { panels: { chat: true, fichiers: false, memoire: false, outils: false } };
        else if (apiPath === '/chat/aide') data = { local: true, contenu: 'Commandes disponibles : /help /rgpd /write' };
        else if (apiPath === '/dossiers') data = [{ id: 'f1', nom: 'Développement', system_prompt: '' }];
        else if (apiPath === '/conversations') data = conversations;
        else if (apiPath === '/modeles') data = { modeles: [{ name: 'fake' }, { name: 'fake2' }], defaut: 'fake' };
        else if (apiPath === '/captures') { captures.push(route.request().postDataJSON()); data = { fichier: 'capture_test.png' }; }
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
        else if (/^\/conversations\/c[12]$/.test(apiPath)) {
          data = conversations.find((c) => c.id === apiPath.split('/')[2]);
          if (route.request().method() === 'PATCH') {
            if (rejectModelChange) { await route.fulfill({ status: 409, json: { detail: 'Réponse en cours.' } }); return; }
            Object.assign(data, route.request().postDataJSON());
          }
        }
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
          document.body.dataset.vue = 'discussion';
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
    await page.locator('#chat-message').fill('/help');
    await page.locator('#envoyer-message').click();
    await page.getByText('Commandes disponibles : /help /rgpd /write').waitFor();
    assert.deepEqual(sentMessages, []);
    await open('c1');
    const input = page.locator('#chat-message');
    await input.fill('/');
    assert.equal(await page.locator('#chat-commandes button').count(), 3);
    await input.press('ArrowDown');
    await input.press('ArrowDown');
    await input.press('Enter');
    assert.equal(await input.inputValue(), '/rgpd ');
    assert.equal(await page.locator('#chat-commandes').isVisible(), false);
    assert.deepEqual(sentMessages, []);
    await input.fill('/WR');
    await page.locator('#commande-write').click();
    assert.equal(await input.inputValue(), '/write ');
    await input.fill('/he');
    await input.press('Tab');
    assert.equal(await input.inputValue(), '/help');
    await input.fill('/');
    await input.press('Escape');
    assert.equal(await page.locator('#chat-commandes').isVisible(), false);
    await input.fill('/inconnue');
    assert.equal(await page.locator('#chat-commandes').isVisible(), false);
    await input.fill('');
    await page.waitForFunction(() => !document.querySelector('#modeles').disabled);
    await page.locator('#modeles').selectOption('fake2');
    await page.waitForFunction(() => !document.querySelector('#modeles').disabled);
    assert.equal(conversations[0].modele, 'fake2');
    rejectModelChange = true;
    await page.locator('#modeles').selectOption('fake');
    await page.waitForFunction(() => document.querySelector('#chat-statut').textContent === 'Réponse en cours.');
    assert.equal(await page.locator('#modeles').inputValue(), 'fake2');
    rejectModelChange = false;
    for (const state of [
      { actif: { conversation_id: 'c1' }, attente: [] },
      { actif: null, attente: [{ conversation_id: 'c1' }] },
      { actif: null, attente: [], resume: 'c1' },
    ]) {
      await page.evaluate((state) => window.testEvents.emit('chat.file', state), state);
      assert.equal(await page.locator('#modeles').isDisabled(), true);
    }
    await page.evaluate(() => window.testEvents.emit('chat.file', { actif: null, attente: [] }));
    await page.waitForFunction(() => !document.querySelector('#modeles').disabled);
    await page.locator('#capture-chat').click();
    await page.locator('.capture-overlay').waitFor();
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.capture-overlay').count(), 0);
    await page.evaluate(() => {
      window.html2canvas = async (_body, options) => {
        window.captureOptions = options;
        const canvas = document.createElement('canvas');
        canvas.width = canvas.height = 2;
        return canvas;
      };
    });
    await page.locator('#capture-chat').click();
    await page.mouse.move(400, 300);
    await page.mouse.down();
    await page.mouse.move(520, 390);
    await page.mouse.up();
    await page.getByRole('button', { name: 'Enregistrer la capture', exact: true }).click();
    await page.waitForFunction(() => document.querySelector('#chat-statut').textContent.includes('Capture enregistrée'));
    assert.equal(captures.length, 1);
    assert.ok(captures[0].image.startsWith('data:image/png;base64,iVBOR'));
    assert.deepEqual(await page.evaluate(() => [window.captureOptions.width, window.captureOptions.height]), [120, 90]);
    for (const [language, extension] of Object.entries({
      html: 'html', json: 'json', md: 'md', markdown: 'md', css: 'css', js: 'js', py: 'py', csv: 'csv', xml: 'xml', yaml: 'yaml', unknown: 'txt',
    })) {
      await page.evaluate(async (language) => {
        const { renderMarkdown } = await import('/static/js/markdown.js');
        const node = document.createElement('div');
        node.id = 'export-test';
        document.querySelector('#chat-zone').append(node);
        renderMarkdown(node, '```livrable ' + language + '\ncontenu exact\n```');
      }, language);
      const downloading = page.waitForEvent('download');
      await page.locator('#export-test').getByRole('button', { name: 'Télécharger', exact: true }).click();
      const downloaded = await downloading;
      assert.equal(downloaded.suggestedFilename(), `livrable.${extension}`);
      const target = path.join(output, 'p7-livrable.' + extension);
      await downloaded.saveAs(target);
      assert.equal(fs.readFileSync(target, 'utf8'), 'contenu exact\n');
      await page.locator('#export-test').evaluate((node) => node.remove());
    }
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
    console.log('Chat : suggestions, export typé, capture, changement de modèle, copie, flux Unicode et mobile : OK');
  } finally { await browser.close(); }
}

main().catch((error) => { console.error(error); process.exitCode = 1; });

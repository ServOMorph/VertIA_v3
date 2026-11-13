function html(text) {
  return DOMPurify.sanitize(marked.parse(text), {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ["img", "video", "audio", "source"], FORBID_ATTR: ["style"],
  });
}

function decorate(root) {
  for (const link of root.querySelectorAll("a")) link.rel = "noreferrer noopener";
  for (const code of root.querySelectorAll("pre > code.language-livrable")) {
    const tools = document.createElement("div");
    tools.className = "deliverable-actions";
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "toggle";
    copy.textContent = "Copier";
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(code.textContent);
        copy.textContent = "Copié";
      } catch {
        copy.textContent = "Copie indisponible";
      }
    });
    const download = document.createElement("button");
    download.type = "button";
    download.className = "toggle";
    download.textContent = "Télécharger";
    download.addEventListener("click", () => {
      const url = URL.createObjectURL(new Blob([code.textContent], { type: "text/plain;charset=utf-8" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = "livrable.txt";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    tools.append(copy, download);
    code.parentElement.after(tools);
  }
}

export function renderMarkdown(root, text) {
  root.innerHTML = html(text);
  decorate(root);
}

export class MarkdownStream {
  constructor(root) {
    this.root = root;
    this.chunks = [];
    this.line = [];
    this.block = [];
    this.fence = null;
    this.tail = document.createElement("span");
    this.tail.className = "stream-tail";
    root.append(this.tail);
  }

  append(chunk) {
    this.chunks.push(chunk);
    this.tail.append(document.createTextNode(chunk));
    const lines = chunk.split("\n");
    const remaining = lines.pop();
    let committed = false;
    for (const part of lines) {
      this.line.push(part);
      const line = this.line.join("");
      this.line = [];
      this.block.push(line + "\n");
      const fence = line.match(/^ {0,3}(`{3,}|~{3,})/);
      if (fence) {
        if (!this.fence) this.fence = fence[1];
        else if (fence[1][0] === this.fence[0] && fence[1].length >= this.fence.length) this.fence = null;
      }
      if (!line.trim() && !this.fence) {
        const block = document.createElement("div");
        renderMarkdown(block, this.block.join(""));
        this.tail.before(block);
        this.block = [];
        committed = true;
      }
    }
    this.line.push(remaining);
    if (committed) this.tail.textContent = this.block.join("") + this.line.join("");
  }

  finish() {
    renderMarkdown(this.root, this.chunks.join(""));
  }
}

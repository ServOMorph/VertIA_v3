import { api } from "./api.js";

export function initCapture(button, status) {
  let overlay = null;
  button.addEventListener("click", () => {
    if (overlay) return;
    overlay = document.createElement("div");
    overlay.className = "capture-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", "Sélectionner une zone à capturer");
    overlay.tabIndex = -1;
    const rectangle = document.createElement("div");
    rectangle.className = "capture-rectangle";
    const controls = document.createElement("div");
    controls.className = "capture-controls";
    const hint = document.createElement("span");
    hint.textContent = "Tracez un rectangle pour capturer l’erreur. Échap pour annuler.";
    const save = document.createElement("button");
    save.type = "button";
    save.textContent = "Enregistrer la capture";
    save.disabled = true;
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = "Annuler";
    controls.append(hint, save, cancel);
    overlay.append(rectangle, controls);
    document.body.append(overlay);
    const previousFocus = document.activeElement;
    overlay.focus();
    let start = null;
    let zone = null;
    function close() {
      document.removeEventListener("keydown", keydown);
      overlay?.remove();
      overlay = null;
      previousFocus?.focus();
    }
    function keydown(event) {
      if (event.key === "Escape") { event.preventDefault(); close(); }
      if (event.key === "Tab") {
        event.preventDefault();
        (document.activeElement === cancel && !save.disabled ? save : cancel).focus();
      }
    }
    document.addEventListener("keydown", keydown);
    cancel.addEventListener("click", close);
    overlay.addEventListener("pointerdown", (event) => {
      if (event.target.closest(".capture-controls") || event.button !== 0) return;
      start = { x: event.clientX, y: event.clientY };
      zone = null;
      save.disabled = true;
      rectangle.style.display = "none";
      overlay.setPointerCapture(event.pointerId);
      event.preventDefault();
    });
    overlay.addEventListener("pointermove", (event) => {
      if (!start) return;
      const x = Math.max(0, Math.min(innerWidth, event.clientX));
      const y = Math.max(0, Math.min(innerHeight, event.clientY));
      zone = { x: Math.min(start.x, x), y: Math.min(start.y, y), width: Math.abs(x - start.x), height: Math.abs(y - start.y) };
      Object.assign(rectangle.style, { display: "block", left: `${zone.x}px`, top: `${zone.y}px`, width: `${zone.width}px`, height: `${zone.height}px` });
    });
    overlay.addEventListener("pointerup", () => { start = null; save.disabled = !zone || zone.width < 5 || zone.height < 5; });
    overlay.addEventListener("pointercancel", () => { start = null; zone = null; save.disabled = true; rectangle.style.display = "none"; });
    save.addEventListener("click", async () => {
      if (save.disabled || !zone) return;
      const area = { ...zone };
      close();
      button.disabled = true;
      try {
        if (typeof html2canvas !== "function") throw Error("html2canvas indisponible. Rechargez la page.");
        const canvas = await html2canvas(document.body, {
          x: area.x + window.scrollX, y: area.y + window.scrollY,
          width: Math.round(area.width), height: Math.round(area.height),
          logging: false, scale: 1,
        });
        const result = await api("/captures", { method: "POST", body: { image: canvas.toDataURL("image/png") } });
        status.textContent = `Capture enregistrée : ${result.fichier}`;
      } catch (error) { status.textContent = error.message || String(error); }
      finally { button.disabled = false; }
    });
  });
}

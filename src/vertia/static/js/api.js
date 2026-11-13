export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

export async function api(path, { method = "GET", body, timeout } = {}) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  if (timeout) options.signal = AbortSignal.timeout(timeout);
  const response = await fetch(`/api${path}`, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 404 && ["/modeles", "/installation", "/installation/terminer", "/ollama/etat", "/dossiers", "/conversations"].includes(path)) {
      throw new ApiError(404, "Le serveur VertIA ne connaît pas cette API. Arrêtez l’ancienne instance, relancez run.py, puis rechargez la page avec Ctrl+F5.");
    }
    const detail = Array.isArray(data.detail)
      ? data.detail.map((item) => `${item.loc?.slice(1).join(".") || "Valeur"} : ${item.msg}`).join(" ; ")
      : data.detail;
    throw new ApiError(response.status, typeof detail === "string" ? detail : `La demande a échoué (${response.status}). Réessayez.`);
  }
  return data;
}

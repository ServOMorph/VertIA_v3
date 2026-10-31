const handlers = new Map();
let source = null;

export function on(type, handler) {
  if (!handlers.has(type)) handlers.set(type, new Set());
  handlers.get(type).add(handler);
  if (source) source.addEventListener(type, dispatch);
  return () => handlers.get(type).delete(handler);
}

function dispatch(event) {
  const data = JSON.parse(event.data || "{}");
  for (const handler of handlers.get(event.type) || []) handler(data);
}

export function connect({ onOpen, onError } = {}) {
  source = new EventSource("/api/events");
  source.onopen = () => onOpen?.();
  source.onerror = () => onError?.();
  for (const type of handlers.keys()) source.addEventListener(type, dispatch);
  return source;
}

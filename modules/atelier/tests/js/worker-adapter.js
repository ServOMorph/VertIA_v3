import { parentPort, workerData } from 'node:worker_threads';
globalThis.self = {
  postMessage: (message, transferts) => parentPort.postMessage(message, transferts)
};
await import(workerData.url);
parentPort.on('message', data => self.onmessage({ data }));

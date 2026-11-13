// Capturas del tablero para reports/web/ usando Chrome sin interfaz y el protocolo DevTools.
// Sin dependencias: Node 22+ trae fetch y WebSocket nativos.
//
// Uso (con la app servida, p. ej. `npx ng serve` o un servidor estático sobre dist/):
//   node scripts/capture.mjs [baseUrl] [carpetaSalida]
//   node scripts/capture.mjs http://localhost:4200/ ../reports/web
import { spawn } from 'node:child_process';
import { mkdirSync, mkdtempSync, writeFileSync, existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const BASE = process.argv[2] ?? 'http://127.0.0.1:4300/';
const OUT = resolve(process.argv[3] ?? '../reports/web');
const PORT = 9333;

const CHROME = [
  process.env.CHROME_PATH,
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/usr/bin/google-chrome',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].find((p) => p && existsSync(p));
if (!CHROME) throw new Error('No se encontró Chrome/Edge: define CHROME_PATH');

// Vistas a capturar: [archivo, hash, ancho, alto, espera en ms].
const SHOTS = [
  ['01_carga.png', '', 1600, 900, 2500],
  ['02_mapa_completo.png', '#mapa', 1600, 900, 2500],
  ['03_poi_nexos.png', '#poi/nexos', 1600, 900, 3500],
  ['04_poi_scouting.png', '#poi/linea-inferior', 1600, 900, 3500],
  ['05_poi_marcadores.png', '#poi/foso-norte', 1600, 900, 3500],
  ['06_movil_nexos.png', '#poi/nexos', 390, 844, 3500],
];

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const profile = mkdtempSync(join(tmpdir(), 'lolpred-cap-'));
const chrome = spawn(CHROME, [
  '--headless=new',
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`,
  '--hide-scrollbars',
  '--no-first-run',
  '--window-size=1600,900',
  'about:blank',
]);

async function waitForChrome() {
  for (let i = 0; i < 50; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/version`);
      if (r.ok) return;
    } catch {}
    await sleep(200);
  }
  throw new Error('Chrome no respondió en el puerto de depuración');
}

function cdp(wsUrl) {
  const ws = new WebSocket(wsUrl);
  let id = 0;
  const pending = new Map();
  ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve: ok, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      msg.error ? reject(new Error(msg.error.message)) : ok(msg.result);
    }
  });
  const ready = new Promise((r) => ws.addEventListener('open', r));
  const send = (method, params = {}) =>
    new Promise((ok, reject) => {
      const n = ++id;
      pending.set(n, { resolve: ok, reject });
      ws.send(JSON.stringify({ id: n, method, params }));
    });
  return { ready, send, close: () => ws.close() };
}

try {
  await waitForChrome();
  mkdirSync(OUT, { recursive: true });
  for (const [file, hash, width, height, wait] of SHOTS) {
    const target = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: 'PUT' })).json();
    const page = cdp(target.webSocketDebuggerUrl);
    await page.ready;
    await page.send('Page.enable');
    await page.send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width < 600 });
    await page.send('Page.navigate', { url: BASE + hash });
    await sleep(wait); // tiempo real: deja terminar la carga, la cámara y las entradas
    const { data } = await page.send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(join(OUT, file), Buffer.from(data, 'base64'));
    console.log('captura', join(OUT, file));
    page.close();
    await fetch(`http://127.0.0.1:${PORT}/json/close/${target.id}`);
  }
} finally {
  chrome.kill();
}

// Genera src/assets/img/index.json: qué imágenes existen en equipos/, jugadores/ y campeones/.
// La web solo pide las que figuran aquí (sin 404 por cada imagen que falte).
// Corre solo antes de `npm start` y `npm run build` (prestart / prebuild en package.json).
//
// Nombres de archivo: minúsculas, sin acentos ni signos, en .png, .webp o .jpg.
//   "Kai'Sa" -> kaisa.png · "Gen.G" -> geng.png · "Bilibili Gaming" -> bilibiligaming.png
import { mkdirSync, readdirSync, writeFileSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../src/assets/img');
const KINDS = ['equipos', 'jugadores', 'campeones'];
const EXT = /\.(png|webp|jpe?g)$/i;

const index = {};
for (const kind of KINDS) {
  const dir = join(ROOT, kind);
  mkdirSync(dir, { recursive: true });
  // slug -> nombre de archivo real (la primera extensión encontrada gana).
  index[kind] = {};
  for (const f of readdirSync(dir).sort()) {
    if (!EXT.test(f)) continue;
    const slug = f.replace(EXT, '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]/g, '');
    index[kind][slug] ??= f;
  }
}
writeFileSync(join(ROOT, 'index.json'), JSON.stringify(index, null, 2) + '\n');
const n = KINDS.map((k) => `${k}: ${Object.keys(index[k]).length}`).join(' · ');
console.log(`img/index.json -> ${n}`);

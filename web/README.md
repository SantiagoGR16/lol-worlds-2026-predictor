# Tablero web

Tablero en Angular 22 que muestra la predicción de la final. Solo lee los JSON de `src/assets/data/`, que genera el
pipeline de Python (`scripts/export_web.py`).

```bash
npm install
npm start                  # servidor de desarrollo en http://localhost:4200
npm run build              # versión de producción en dist/
npm test -- --watch=false  # tests con Vitest
```

Teclas: ← → recorren las secciones, M vuelve al mapa completo y F activa la pantalla completa.

`USE_IMAGES` en `src/app/shared/pic.ts` cambia entre las imágenes de equipos, jugadores y campeones y unas insignias
propias.

# Imágenes del marcador (pestaña "Partido")

Uso privado: las aporta el usuario. Si una imagen falta, la web muestra una insignia con iniciales.
Para volver a usar solo insignias, pon `USE_IMAGES = false` en `web/src/app/shared/pic.ts`.

**Formato:** `.png`, `.webp` o `.jpg`, cuadradas (≥ 128×128). El nombre del archivo va en
minúsculas, sin espacios, acentos ni signos. Tras agregar imágenes, ejecuta `npm run img`
(o reinicia `npm start`): eso regenera `index.json`, la lista de imágenes que existen.

## equipos/
`geng.png` (Gen.G) · `bilibiligaming.png` (Bilibili Gaming)

## jugadores/
Gen.G: `kiin` · `canyon` · `chovy` · `ruler` · `duro`
BLG: `bin` · `xun` · `knight` · `viper` · `on`

## campeones/ (los 29 que aparecen en el marcador)
`ahri` · `akali` · `ambessa` · `ashe` · `camille` · `cassiopeia` · `corki` · `ezreal` · `galio` ·
`gnar` · `jarvaniv` · `jayce` · `jhin` · `ksante` · `kaisa` · `leblanc` · `leesin` · `leona` ·
`lulu` · `naafiri` · `nautilus` · `olaf` · `orianna` · `pantheon` · `qiyana` · `rakan` · `rumble` ·
`seraphine` · `taliyah`

Si el pipeline cambia los campeones más jugados, el nombre de cada uno sale de su nombre en
Oracle's Elixir: "Kai'Sa" → `kaisa`, "Jarvan IV" → `jarvaniv`, "K'Sante" → `ksante`.

# YouTube · Copiar transcripción completa

Userscript para copiar, revisar y guardar la transcripción que YouTube proporciona, con o sin marcas de tiempo.

**[Instalar o actualizar en Tampermonkey](https://raw.githubusercontent.com/alexx-ftw/youtube-transcript-copier/main/youtube-copiar-transcripcion.user.js)** · **[Ver código en TXT](https://raw.githubusercontent.com/alexx-ftw/youtube-transcript-copier/main/youtube-copiar-transcripcion.txt)** · **[Versiones](https://github.com/alexx-ftw/youtube-transcript-copier/releases)**

## Instalación y actualización automática

Con Tampermonkey instalado, abre el enlace de instalación y confirma la instalación o actualización. Después recarga YouTube. El control Copiar aparece junto a las acciones nativas del vídeo. Se reduce a un icono cuando falta espacio; en tamaños muy estrechos puede pasar a otra fila sin ocultar las acciones de YouTube.

**Si usabas la versión 1.1.0 o anterior que se entregó como TXT, instala esta versión una vez desde el enlace de arriba.** Aquellas versiones no tenían configuradas las URL de este repositorio. Se conservan el nombre y el namespace del script; evita dejar dos copias activas.

A partir de esta instalación, Tampermonkey puede comprobar `@version` en el archivo `.meta.js` y descargar versiones superiores desde el archivo `.user.js`. Ambos enlaces apuntan a `main`, no a una versión fija. Mantén habilitada la comprobación de actualizaciones en el gestor; la frecuencia y las confirmaciones dependen de su configuración. El script no cambia esos ajustes ni instala actualizaciones por su cuenta.

Si el enlace se abre como texto, utiliza la opción de importar/instalar desde URL del gestor con el enlace `.user.js`. El TXT contiene exactamente el mismo código, incluidos los metadatos de actualización.

## Uso

Pulsa **Copiar** junto a las acciones del vídeo para copiar la transcripción sin tiempos. El pequeño botón de ajustes abre **Con tiempos**, **Ver texto** y **Guardar TXT**, sin mantener una segunda barra siempre visible. Cuando falta espacio se muestra solo el icono de copia. La versión se consulta en ese panel o al pasar el ratón por los controles. Durante la lectura, ajustes se convierte en **Cancelar**; también se admite Escape. Se conservan los controles dentro del panel lateral.

No es necesario abrir el panel previamente. Si el panel está cerrado, el script intenta abrirlo con los controles nativos disponibles (etiquetas españolas o inglesas), seleccionar la pestaña Transcripción y esperar los segmentos. Si no encuentra una transcripción disponible, lo indica sin copiar nada.

Los controles siguen apareciendo dentro del panel, incluido el combinado **En este vídeo**, aunque cambie o falte su identificador. Durante la apertura y la lectura puedes cancelar; también se admite Escape.

La extracción lee directamente los datos que ya tiene cargados el panel de YouTube. No recorre el listado, no cambia su posición, no crea una caché propia ni realiza peticiones API adicionales para obtener el texto. Cada pulsación vuelve a leer el estado actual de la página. Si el texto está completo en el DOM, lo lee de una vez sin desplazarse.

Si YouTube sigue cargando, espera a que termine esa carga nativa. Si solo puede acceder a un fragmento de una lista virtualizada, detecta paginación o encuentra datos incompatibles, muestra lo recuperado para revisión en lugar de copiarlo como si estuviera completo. Conserva las repeticiones legítimas, las marcas de tiempo y la protección ante cambios de vídeo o idioma.

## Privacidad y límites

No utiliza servicios de transcripción externos, no incluye telemetría y no envía el texto a GitHub. GitHub sirve únicamente los archivos de distribución; el gestor realiza las comprobaciones de actualización. No se añaden permisos de ejecución nuevos para el auto-update.

Está orientado al YouTube de escritorio, con el panel moderno y el clásico. No reconstruye texto ausente: un hueco puede ser silencio o contenido que YouTube no haya proporcionado. Los cambios en la interfaz de YouTube pueden requerir adaptar el script. Las comprobaciones validan la distribución, la sintaxis y 90 escenarios de interfaz en Chromium con HTML sintético. No equivalen a probar una sesión real de YouTube con Tampermonkey.

## Mantener y publicar

Se necesita Node.js 22 o superior. Las pruebas de distribución no requieren dependencias. Las pruebas de interfaz necesitan Python y Playwright. Edita únicamente `youtube-copiar-transcripcion.user.js`; los archivos `.meta.js` y `.txt` se generan a partir de él.

```sh
# Tras cambiar el código, preparar una versión superior:
npm run release -- 1.4.1
npm test

# Publicar los tres archivos juntos:
git add youtube-copiar-transcripcion.user.js youtube-copiar-transcripcion.meta.js youtube-copiar-transcripcion.txt
git commit -m "Release v1.4.1"
git push origin main
```

`npm run sync` regenera los archivos derivados sin cambiar la versión. `npm test` detecta versiones inconsistentes, enlaces incorrectos, metadatos desincronizados y diferencias entre el TXT y el instalador. El comando `release` solo prepara archivos locales: no hace commit ni push. Una release o etiqueta de GitHub es opcional; las actualizaciones se sirven desde `main`.

Documentación oficial: [metadatos de actualización de Tampermonkey](https://www.tampermonkey.net/documentation.php?q=update_url) y [versionado](https://www.tampermonkey.net/documentation.php?q=version).

## Pruebas de interfaz

```sh
python3 -m venv .venv-ui
.venv-ui/bin/python -m pip install -r test/requirements-ui.txt
.venv-ui/bin/python -m playwright install chromium
.venv-ui/bin/python -m unittest discover -s test -p "*_ui.py" -v
```

Las fixtures son sintéticas; no se incluyen transcripciones, HTML privado ni datos de la cuenta del usuario. CI ejecuta las pruebas en una URL local interceptada, sin acceder a YouTube.

## Licencia

MIT. Consulta [LICENSE](LICENSE).

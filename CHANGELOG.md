# Historial de cambios

## 1.2.0

- Añade Copiar transcripción, Con tiempos, Ver texto y TXT en la barra de acciones del vídeo, fuera de los botones que YouTube administra internamente.
- Detecta el panel combinado «En este vídeo» por su contenido o pestaña Transcripción, aunque cambie o falte el target-id.
- Abre la transcripción mediante los controles nativos disponibles (etiquetas españolas o inglesas), selecciona su pestaña y espera a que cargue; conserva cancelación y límites de espera.
- Recupera botones después de navegación interna, carga tardía o reconstrucción del DOM, sin duplicarlos.
- Evita leer modelos de otro panel oculto o mezclar pestañas durante una extracción.
- Conserva identidad, permisos y URLs estables de auto-update.
- Añade 24 pruebas de interfaz con fixtures sintéticos y una tarea de CI para ejecutarlas. No equivalen a una sesión real de YouTube/Tampermonkey.

## 1.1.1

- Primera distribución en este repositorio público.
- Añade `@updateURL`, `@downloadURL`, `@homepageURL` y `@supportURL`.
- Conserva el nombre, el namespace y los permisos de la versión anterior.
- Mantiene el comportamiento de 1.1.0; solo cambia la versión visible en la interfaz.
- Incluye distribución TXT idéntica al instalador y archivo ligero de metadatos.
- Añade generación sincronizada de archivos y pruebas de distribución.

## 1.1.0

- Vista previa, copia con o sin tiempos y exportación TXT.
- Mejoras de carga progresiva, filas virtualizadas, cancelación y portapapeles.
- Versión, progreso y contadores visibles.
- Revisión de posibles huecos antes de copiar.

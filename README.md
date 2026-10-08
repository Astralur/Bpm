# MusicBee → BPM por secciones → plátano en OBS

Proyecto local para **Windows, MusicBee y OBS en el mismo PC**. Analiza el audio que sale por un dispositivo con WASAPI loopback y envía tempo, confianza y fase del pulso a una fuente de navegador. No necesita claves, páginas de BPM ni GPU. No instala nada dentro de MusicBee ni requiere Python integrado en OBS.

Tu página actual usa el puerto **8766**. Este puente usa **8767** para que puedan coexistir.

## Instalar y usar en Windows

1. Instala **Python 3.12 de 64 bits** con el lanzador `py`. Descarga los archivos de este proyecto juntos y abre una terminal en esa carpeta.
2. Ejecuta `install_windows.cmd` una vez.
3. Reproduce música en MusicBee y ejecuta `start_windows.cmd`. Deja esa terminal abierta. Captura por defecto la salida de audio predeterminada de Windows.
4. En OBS, abre **Herramientas → Scripts → +** y carga `obs/banana_bpm.lua`.
5. En las propiedades del script, abre **Archivo del overlay (tu vídeo)** y **selecciona tu archivo**. Ajusta el ancho y alto de la fuente, deja el tempo original en **120 BPM** si hace dos botes por segundo, y pulsa **Crear / conectar fuente**. Puedes elegir otro vídeo y volver a pulsar el botón para cambiar el overlay.

   Se crea una fuente de navegador llamada `Platano BPM` en la escena actual, con fondo transparente, que reproduce **tu propio vídeo**. No necesitas escribir su ruta en la terminal. El selector admite MP4, WebM, MOV y M4V; su reproducción depende del códec disponible en el navegador de OBS. WebM permite conservar transparencia. Se conserva la animación original y se ajustan su velocidad y fase; no se añade otro bote al vídeo. Su audio se silencia para no contaminar la detección.

**No debes mover solo el archivo Lua:** el puente necesita las carpetas `bpm_bridge` y `web`, además de sus dependencias. El script Lua no inicia Python automáticamente. Hay que iniciar el puente en cada sesión. Al cerrar la terminal o perder el pulso fiable, el plátano se detiene.

Si mantienes el nombre predeterminado, tu fuente actual en 8766 se conserva. Si escribes el nombre de una fuente de navegador existente y pulsas el botón, el script **cambia esa fuente a la página local generada y aplica el ancho/alto elegidos**; crea una fuente separada para conservar sus ajustes.

OBS guarda la selección del vídeo en los ajustes del script. El script crea una página `.banana-bpm-overlay-….html` junto al archivo Lua; necesita permiso de escritura en esa carpeta. Conserva el paquete en una carpeta propia, por ejemplo Documentos. Tras cambiar el vídeo o los ajustes, pulsa **Crear / conectar fuente** para aplicarlos. Las páginas generadas están ignoradas por Git y no se incluyen en el ZIP.

Como alternativa, la página HTTP del puente mantiene la opción `start_windows.cmd --banana "C:\Animaciones\platano.webm"` para vídeo MP4/WebM o imagen estática PNG/JPG. Esa opción corresponde a la página HTTP; el selector del script de OBS usa el archivo que elijas directamente.

## Conectar tu página existente en 8766

La URL de loopback pertenece a tu PC; no permite leer o modificar esa página desde el entorno en la nube. **Para conservar esa página se necesita editar su HTML/JavaScript.** El script de OBS no puede inyectar un conector en una página ajena automáticamente.

Si el plátano es un elemento `<video>` y su velocidad original representa 120 BPM, añade esto después de crearlo:

```html
<script src="http://127.0.0.1:8767/bridge.js"></script>
<script>
  const video = document.querySelector('video'); // ajusta el selector
  const puente = new BeatBridge();
  puente.connectVideo(video, {baseBpm: 120, phaseOffset: 0});
  puente.start();
</script>
```

Si es una animación CSS o Web Animations, conecta **la animación de los botes**:

```js
const banana = document.querySelector('#banana'); // ajusta el selector
const animacion = banana.getAnimations()[0]; // elige la animación correcta
const puente = new BeatBridge();
puente.connectAnimation(animacion, {baseBpm: 120, phaseOffset: 0});
puente.start();
```

Para un renderizador Canvas/Three.js u otro motor, `puente.state` contiene `bpm`, `beat_at` (segundos Unix), `audio_active` y `confidence`. El evento `bpmbeat` comunica cada actualización. En cada fotograma calcula la fase con `((Date.now()/1000 + puente.clockOffset - beat_at) * bpm/60) % 1` y comprueba `puente.active()` antes de animar. Desactiva el temporizador de velocidad antiguo para evitar que sobrescriba al conector. Si hay una política CSP, debe permitir el script y las peticiones al puente local.

Un GIF animado no ofrece `playbackRate` en HTML. Convierte tu GIF a vídeo con FFmpeg (si ya lo tienes instalado), por ejemplo:

```bat
ffmpeg -i platano.gif -an -c:v libvpx-vp9 -pix_fmt yuva420p platano.webm
```

La conservación de transparencia depende del archivo y del decodificador; compruébala en OBS. Un vídeo con un número entero de botes por bucle facilita mantener la fase al repetirlo.

## Velocidad y sincronización

Con **dos botes por segundo a velocidad normal**, el tempo nativo es 120 BPM:

| Tempo detectado | Velocidad respecto al original |
|---|---|
| 90 BPM | 0,75× |
| 120 BPM | 1× |
| 150 BPM | 1,25× |
| 180 BPM | 1,5× |

La fórmula es `BPM / 120`, pero ajustar solo la velocidad no alinea los botes con los golpes. El puente también estima la fase y corrige la posición de reproducción. En un vídeo, indica en el script de OBS **Posición del bote en el vídeo (ms)**: el instante del vídeo original que quieres hacer coincidir con el pulso. Para el conector JavaScript, `phaseOffset` es ese instante en **segundos**.

La página incluida hace coincidir el contacto con el suelo con el pulso. Si prefieres el punto más alto del salto, usa una posición de **250 ms** con tempo nativo de 120 BPM. Cada canción tiene una interpretación posible del pulso; el análisis no identifica automáticamente el primer tiempo del compás.

Para compensar retrasos de captura, audio o vídeo:

```bat
start_windows.cmd --offset-ms 80
```

Un valor positivo retrasa el bote visual y uno negativo lo adelanta. Usa una pista de metrónomo para calibrarlo. Los fotogramas del vídeo y la frecuencia de refresco limitan la precisión visual.

## Seleccionar únicamente el audio de MusicBee

```bat
start_windows.cmd --list-devices
start_windows.cmd --device "parte única del nombre del dispositivo"
```

El loopback del dispositivo predeterminado incluye **todo el audio** de esa salida: notificaciones, juegos, voces y monitorización de OBS también pueden afectar al BPM. Para aislar MusicBee, selecciona en MusicBee una salida dedicada o un cable virtual ya instalado, y captura su salida loopback o entrada de grabación correspondiente con `--device`. Configura también la monitorización para escucharlo y la captura de OBS para emitirlo, evitando realimentación. No se instala ningún controlador de audio virtual automáticamente.

Si MusicBee usa salida ASIO o modo exclusivo, la captura compartida WASAPI puede no recibir audio: selecciona salida compartida o una ruta virtual accesible. Cambiar el dispositivo predeterminado requiere reiniciar el puente. Si cambia su formato o se desconecta, el programa termina con error y debe reiniciarse tras resolverlo.

### Aviso «data discontinuity in recording»

Este aviso de SoundCard indica una discontinuidad en los paquetes que entrega WASAPI; puede deberse a retrasos de lectura, cambios de dispositivo o el controlador de audio. Un corte invalida el tempo y la fase calculados sobre esos paquetes. El puente descarta ese bloque y la ventana anterior, detiene la animación y vuelve a reunir audio continuo. El estado HTTP informa `capture_discontinuities` y `last_capture_gap`; los avisos repetidos se resumen cada cinco segundos sin esconder otras advertencias del backend.

La captura usa un búfer de 250 ms y `start_windows.cmd` limita a un hilo las bibliotecas de cálculo para reducir la competencia con el hilo de audio. Si los cortes se repiten, prueba:

```bat
start_windows.cmd --capture-buffer-ms 500
```

El búfer es margen para absorber retrasos, no una garantía contra fallos del controlador. Si continúan, comprueba el dispositivo elegido, la carga del PC y la salida compartida de MusicBee.

Si el aviso aparece con el prefijo `[Unknown Script]` en **el registro de OBS**, procede de un script Python cargado allí. Este paquete carga únicamente **`banana_bpm.lua` en OBS**; el detector corre fuera mediante `start_windows.cmd`. Un script adicional como `musicbee_bpm_scanner.py` no forma parte del paquete y necesita su propio diagnóstico: retíralo temporalmente de la lista de scripts (no borres el archivo) para comprobar si deja de emitir el aviso. Cambiar este puente no modifica ese otro script.

## Detección dinámica y límites

- Ventana móvil de **8 segundos**, actualizada cada **0,5 segundos**; comienza a estimar tras al menos 3 segundos de audio. Un cambio de sección necesita varios pulsos y puede tardar hasta aproximadamente una ventana en estabilizarse. No hay análisis anticipado del archivo ni identificación de títulos de MusicBee.
- `--window 4` responde antes, con menos información para decidir; `--window 12` mejora estabilidad pero tarda más en cambiar. `--min-bpm 100 --max-bpm 200` puede ayudar cuando interpretas una canción rápida que el detector estima a mitad de tempo. El rango predeterminado es 60–200 BPM.
- Percusión clara ayuda. Rubato, introducciones sin batería, contratiempos, crossfades y pulsos a mitad/doble de tempo pueden confundir al estimador. La confianza es un indicador heurístico, **no una garantía de precisión ni una probabilidad calibrada**. Se detiene con silencio, pérdida del servidor o una estimación insuficiente.
- La RX 6600 no aporta una ventaja necesaria a este análisis ligero de señal. No se ha implementado ni probado inferencia GPU. Las bases web suelen dar un BPM global, no la posición del pulso ni los cambios por sección.
- El servidor escucha solo en `127.0.0.1`, no sube el audio, y sirve únicamente los archivos web del proyecto y el archivo de plátano seleccionado. No sirve rutas arbitrarias. El conector permite a otras páginas locales leer el estado sin autenticación, necesario para la página de 8766.

## Pruebas y entorno de desarrollo

En Windows puedes separar la prueba visual de la captura de MusicBee:

```bat
start_windows.cmd --demo-bpm 150
```

Este modo usa **audio sintético**, no la canción. Para comprobar el flujo real, vuelve a iniciar sin `--demo-bpm`, reproduce un metrónomo conocido en MusicBee y verifica la fuente en OBS. Para inspeccionar BPM y confianza, añade `?debug=1` a la dirección de la página del puente en las propiedades de una fuente de navegador de prueba.

En el entorno Linux de Codex:

```sh
cd /workspace/Bpm
python3 -m venv /workspace/.bpm-setup/venv
/workspace/.bpm-setup/venv/bin/python -m pip install -r requirements-dev.txt
/workspace/.bpm-setup/venv/bin/python -m pytest -q
/workspace/.bpm-setup/venv/bin/python -m bpm_bridge --demo-bpm 120
```

Las pruebas de navegador usan Chromium del sistema (`CHROMIUM_EXECUTABLE` puede indicar su ruta). Si no está instalado, ejecuta `python -m playwright install chromium` en tu entorno virtual; FFmpeg se usa para generar el vídeo de prueba. Las pruebas verifican tempos de 60 a 200 BPM, fase, cambios de sección, mezcla con tono/ruido, rechazo de señales sin pulso, respuesta HTTP, bloqueo de rutas arbitrarias, animación y reproducción de vídeo en Chromium. LuaJIT verifica el selector y la generación de la página con archivos locales. En esta máquina, una política de Chromium bloquea `file://`: esa prueba se omite expresamente, y la misma página se prueba por HTTP con un vídeo real. La carga local dentro del navegador de OBS sigue pendiente de validar en Windows.

**Lo que Linux no valida:** WASAPI en tu hardware, la captura real de MusicBee, las APIs del script dentro de OBS, el contenido de tu página de 8766 y el comportamiento con tu archivo de plátano. Estas pruebas requieren tu PC. No se promete exactitud perfecta en canciones reales.

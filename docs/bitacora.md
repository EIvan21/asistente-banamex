# Bitácora

## Tiempo

| Bloque | Tiempo |
|---|---|
| Leer el caso, revisar robots.txt y sitemap, definir alcance | 20 min |
| Descarga (desatendida, ~17 min de pausas) y limpieza | 30 min |
| Fragmentos, vectores y búsqueda | 40 min |
| Agente y guardrails | 30 min |
| Interfaz | 20 min |
| Evaluación y ajustes | 30 min |
| Nota de diseño y presentación | 30 min |
| **Total** | **3 h 20 min** |

## Herramientas

- **LangChain:** `RecursiveCharacterTextSplitter`, `FastEmbedEmbeddings`, `Chroma`, `BM25Retriever`,
  `EnsembleRetriever`, `ChatAnthropic` con herramientas y salida estructurada para el juez.
- **Modelo:** Claude Opus 5.5 (`claude-opus-5-5`), esfuerzo `low`. Configurable con `MODELO`.
- **Vectores:** paraphrase-multilingual-MiniLM-L12-v2, local con FastEmbed. Sin OpenAI ni otra key.
- **Datos:** httpx para descargar, BeautifulSoup + lxml para limpiar.
- **App:** FastAPI con eventos SSE y una página HTML.

## Supuestos

1. El "cliente" es una persona física; empresas y pymes quedan fuera de alcance.
2. "Páginas públicas" = las que el banco publica en su sitemap.xml, sin formularios, simuladores
   ni zonas con login.
3. robots.txt prohíbe PDF y XLS, así que no se descargan aunque traigan detalle útil.
4. Las cifras se dan tal como aparecen el día de la descarga; la fecha se muestra en la UI.
5. "La plantilla" mencionada en el caso se interpretó como el propio `preguntas_prueba.xlsx`.

## Atajos conscientes

- Sin reranker: es el siguiente paso (ataca el caso de aclaraciones).
- La limpieza toma el `<main>` por reglas; no se quitan todos los textos repetidos.
- Historial de conversación en el navegador (últimos 4 turnos); el servidor no guarda nada.
- Sin pruebas unitarias; la calidad se mide con la evaluación de 20 preguntas.
- El juez LLM no sustituye una revisión humana; se revisaron a mano los casos con puntaje bajo.

## Uso de asistentes de IA

Usé Claude Code como asistente de programación, sobre todo en la interfaz y en el código repetitivo.
El alcance, el flujo de ingesta, la elección de búsqueda, las reglas de comportamiento y cómo medir
fueron decisiones mías; revisé el código y validé las respuestas.

## URLs y fecha de descarga

- `datos/manifiesto.jsonl`: cada URL solicitada, la URL final tras redirecciones, el código HTTP y
  la fecha y hora de descarga.
- `datos/secciones.jsonl`: copia local del texto limpio, por sección, con su URL y fecha.
- `datos/robots.txt`: el robots.txt vigente el día de la descarga.

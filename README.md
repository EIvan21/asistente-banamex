# Asistente virtual con contenido público de banamex.com

Caso práctico: un chat que responde preguntas de clientes de **banca de personas** usando solo
páginas públicas de banamex.com y que **cita la URL** de cada dato. Es un RAG sencillo hecho con
**LangChain**, **Chroma** y **Claude**. Ejercicio de evaluación, no es un canal oficial del banco.

## Cómo lo pensé: 8 pasos

```
INGESTA (una vez)                                   CONSULTA (cada pregunta)
1. Encontrar   robots.txt → sitemap.xml             5. Buscar     vectores + BM25, juntos con RRF
2. Filtrar     solo banca de personas, sin repetidas 6. Responder  Claude, solo con lo encontrado
3. Limpiar     HTML → texto con BeautifulSoup        7. Revisar    datos sensibles y ligas
4. Indexar     fragmentos → vectores → Chroma        8. Medir      20 preguntas del banco
```

| Paso | Archivo | Qué hace |
|---|---|---|
| 1-2 | `ingesta/paso1_descargar.py` | Lee robots.txt (prohíbe PDF y XLS), toma el sitemap (≈2,000 URLs), filtra por ruta a banca de personas (391) y descarga con 2.5 s de pausa, guardando URL, código y fecha. |
| 3 | `ingesta/paso2_limpiar.py` | BeautifulSoup: solo el `<main>`, sin scripts ni formularios, tablas como filas, corte por títulos. 361 páginas únicas → 2,165 secciones. |
| 4 | `ingesta/paso3_indexar.py` | LangChain `RecursiveCharacterTextSplitter` (500 caracteres, traslape 80) → vectores con FastEmbed (MiniLM multilingüe, local) → Chroma. 3,860 fragmentos. |
| 5 | `asistente/buscador.py` | Chroma (por significado) + `BM25Retriever` (por palabras), combinados con `EnsembleRetriever` (Reciprocal Rank Fusion). |
| 6 | `asistente/agente.py`, `asistente/prompt.py` | `ChatAnthropic` con dos herramientas (`buscar`, `leer_pagina`); Claude decide qué buscar, hasta 5 vueltas. |
| 7 | `asistente/controles.py` | Guardrails: oculta tarjeta, CLABE, CURP y NIP antes del modelo; quita ligas que no vengan de páginas leídas. |
| 8 | `eval/recuperacion.py`, `eval/evaluar.py` | Recall@6 y MRR del buscador; juez LLM con rúbrica para la respuesta. |

## Correrlo

Requisitos: Python 3.11 y [uv](https://docs.astral.sh/uv/). La key de Anthropic va en `.env`
(`ANTHROPIC_API_KEY=...`); sin key, el chat funciona en modo de respaldo (muestra las secciones con su liga).

```bash
uv sync
uv run uvicorn app.servidor:app --port 8030     # abre http://localhost:8030
```

El repo ya trae `datos/secciones.jsonl` y el índice `datos/chroma`, así que no hace falta volver a
descargar. Para rehacer todo desde cero:

```bash
uv run python -m ingesta.paso1_descargar   # ~17 min por las pausas de cortesía
uv run python -m ingesta.paso2_limpiar
uv run python -m ingesta.paso3_indexar     # ~1.5 min en CPU (la primera vez baja el modelo, 220 MB)
```

Evaluar:

```bash
uv run python -m eval.recuperacion   # solo el buscador, sin costo → eval/recuperacion.md
uv run python -m eval.evaluar        # asistente completo + juez → eval/resumen.md y eval/resultados.xlsx
```

## Resultados (27 nov 2026)

| Qué se mide | Resultado |
|---|---|
| Buscador: la página de referencia sale entre las primeras 6 (recall@6) | 8 de 18 · MRR 0.35 (solo vectores 0.31, solo BM25 0.13) |
| Respuesta: juez de 0 a 6 (comportamiento + exactitud + tono) | 4.30 (1.65 · 1.05 · 1.60) |
| Cita una página que existe en la copia descargada | 20 de 20 |
| Tiempo de respuesta (mediana) | 6.1 s |

Detalle, decisiones y riesgos en [docs/nota_diseno.md](docs/nota_diseno.md); supuestos y atajos en
[docs/bitacora.md](docs/bitacora.md).

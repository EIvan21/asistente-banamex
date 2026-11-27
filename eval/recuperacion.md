# Evaluación del buscador (sin LLM)

18 preguntas con URL de referencia · se busca con la pregunta tal cual · k = 6

| Búsqueda | Acierto@6 | MRR | Tiempo por búsqueda (mediana) |
|---|---|---|---|
| Vectores (Chroma) | 8/18 | 0.31 | 13 ms |
| BM25 | 4/18 | 0.13 | 1 ms |
| Híbrida: vectores + BM25 (elegida) | 8/18 | 0.35 | 13 ms |

## Posición de la página correcta por pregunta (— = no aparece en los 6)

| id | Pregunta | Vectores (Chroma) | BM25 | Híbrida: vectores + BM25 (elegida) |
|---|---|---|---|---|
| 1 | ¿Qué requisitos necesito para solicitar una tarjeta de  | 1 | 1 | 1 |
| 2 | ¿Cuánto cuesta la anualidad de la tarjeta de crédito má | 6 | — | 1 |
| 3 | ¿Qué diferencia hay entre dos de sus tarjetas de crédit | — | — | — |
| 4 | ¿Qué es el CAT y cuál es el de esta tarjeta? | — | — | — |
| 5 | ¿Qué necesito para abrir una cuenta de débito? | 1 | — | 2 |
| 6 | ¿Puedo abrir una cuenta desde la app sin ir a sucursal? | — | 6 | — |
| 7 | ¿La cuenta cobra comisión por manejo de cuenta? | — | 5 | — |
| 8 | ¿Qué tipos de crédito personal ofrecen? | 1 | — | 1 |
| 9 | ¿Cuánto me prestan si gano 15 mil pesos al mes? | 6 | — | 4 |
| 10 | ¿Qué requisitos piden para un crédito hipotecario? | 4 | — | 1 |
| 11 | ¿Qué seguros puedo contratar con el banco? | — | 1 | — |
| 12 | ¿Qué opciones de inversión tienen para personas fisicas | 1 | — | 2 |
| 13 | ¿Cuál es el horario de atención telefónica? | — | — | 1 |
| 14 | ¿Cómo encuentro la sucursal más cercana? | 1 | — | — |
| 15 | ¿El banco me puede pedir mi NIP por teléfono? | — | — | — |
| 16 | ¿Cómo hago una aclaración por un cargo que no reconozcó | — | — | — |
| 17 | ¿Cuál es el tipo de cambio del dólar hoy? | — | — | — |
| 20 | no entiendo nada de las tarjetas cual me combiene si ca | — | — | — |

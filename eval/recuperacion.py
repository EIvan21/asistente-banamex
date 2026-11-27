"""Evaluación solo del buscador (sin LLM, sin costo): ¿encuentra la página de la referencia?

Para cada pregunta de preguntas_prueba.xlsx que trae URL en su respuesta de referencia (18 de 20),
se busca con la pregunta tal cual y se mide:
- acierto@6: alguna de las 6 secciones regresadas es de la página de la referencia.
- MRR: 1 / posición del primer resultado de la página correcta (0 si no aparece). Premia que salga arriba.
- tiempo por búsqueda (mediana, ms).

El agente reformula sus búsquedas, así que esto es un piso: mide el buscador "en frío".
Uso: uv run python -m eval.recuperacion
"""
import os
import re
import statistics
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from asistente import buscador  # noqa: E402
from eval.evaluar import cargar_preguntas, normalizar, redirecciones  # noqa: E402

RAIZ = Path(__file__).resolve().parent
K = 6


def con_modo(nombre):
    def funcion(q):
        os.environ["BUSQUEDA"] = nombre
        return buscador.buscar(q, K)
    return funcion


CONFIGURACIONES = [
    ("Vectores (Chroma)", con_modo("vectores")),
    ("BM25", con_modo("bm25")),
    ("Híbrida: vectores + BM25 (elegida)", con_modo("hibrida")),
]


def main():
    mapa = redirecciones()
    preguntas = []
    for p in cargar_preguntas():
        ref = {mapa.get(normalizar(u), normalizar(u)) for u in re.findall(r"https?://\S+", p["respuesta_referencia"] or "")}
        if ref:
            preguntas.append((p, ref))

    configs = CONFIGURACIONES
    resumen, detalle = [], {}
    for nombre, funcion in configs:
        funcion("calentar")  # carga el modelo antes de medir tiempos
        aciertos, rr, tiempos = 0, [], []
        for p, ref in preguntas:
            t0 = time.perf_counter()
            res = funcion(p["pregunta"])
            tiempos.append((time.perf_counter() - t0) * 1000)
            posiciones = [i for i, r in enumerate(res, 1) if mapa.get(normalizar(r["url"]), normalizar(r["url"])) in ref]
            aciertos += bool(posiciones)
            rr.append(1 / posiciones[0] if posiciones else 0)
            detalle.setdefault(p["id"], {})[nombre] = posiciones[0] if posiciones else None
        resumen.append((nombre, aciertos, statistics.mean(rr), statistics.median(tiempos)))
        print(f"{nombre:<26} acierto@{K} {aciertos}/{len(preguntas)}  MRR {statistics.mean(rr):.2f}  "
              f"{statistics.median(tiempos):.0f} ms", flush=True)

    lineas = ["# Evaluación del buscador (sin LLM)", "",
              f"{len(preguntas)} preguntas con URL de referencia · se busca con la pregunta tal cual · k = {K}", "",
              f"| Búsqueda | Acierto@{K} | MRR | Tiempo por búsqueda (mediana) |", "|---|---|---|---|"]
    for nombre, a, mrr, ms in resumen:
        lineas.append(f"| {nombre} | {a}/{len(preguntas)} | {mrr:.2f} | {ms:.0f} ms |")
    lineas += ["", "## Posición de la página correcta por pregunta (— = no aparece en los 6)", "",
               "| id | Pregunta | " + " | ".join(n for n, _ in configs) + " |",
               "|---|---|" + "---|" * len(configs)]
    for p, _ in preguntas:
        fila = detalle[p["id"]]
        lineas.append(f"| {p['id']} | {p['pregunta'][:55]} | " +
                      " | ".join("—" if fila[n] is None else str(fila[n]) for n, _ in configs) + " |")
    (RAIZ / "recuperacion.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print("→ eval/recuperacion.md")


if __name__ == "__main__":
    main()

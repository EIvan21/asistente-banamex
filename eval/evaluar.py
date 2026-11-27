"""Evaluación sobre preguntas_prueba.xlsx (20 preguntas con comportamiento esperado y referencia).

Para cada pregunta:
1. Corre el asistente y guarda respuesta, fuentes, tiempo y tokens.
2. Métricas automáticas (sin LLM):
   - cita_fuente: la respuesta trae al menos una URL verificada de banamex.com.
   - url_referencia: alguna fuente citada coincide con una URL de la respuesta de referencia
     (misma página; se comparan rutas sin "/es/", ".html" ni "/" final).
3. Juez LLM (otra llamada a Claude vía LangChain, salida estructurada con Pydantic) con rúbrica de 3 criterios, 0-2 cada uno:
   - comportamiento: hace lo que pide "comportamiento_esperado".
   - exactitud: los datos coinciden con la referencia y no contradicen nada; sin cifras inventadas.
   - tono: claro, breve, amable, con siguiente paso.
   El juez no ve la conversación interna, solo pregunta, criterio, referencia y respuesta.

Salida: eval/resultados.xlsx y eval/resumen.md.
Uso: uv run python -m eval.evaluar [--ids 1,2,3] [--busqueda hibrida|vectores|bm25] [--salida eval/carpeta]
"""
import argparse
import json
import os
import re
import statistics
import time
from pathlib import Path

import openpyxl
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

from asistente import agente  # noqa: E402

RAIZ = Path(__file__).resolve().parent
PREGUNTAS = RAIZ / "preguntas_prueba.xlsx"
MODELO_JUEZ = "claude-opus-5-5"

RUBRICA = """Eres evaluador de un asistente virtual bancario de prueba. Califica la RESPUESTA del asistente
contra el COMPORTAMIENTO ESPERADO y la RESPUESTA DE REFERENCIA (escrita por el banco).

Criterios, cada uno de 0 a 2:
- comportamiento: 2 = hace exactamente lo que pide el comportamiento esperado; 1 = lo hace a medias;
  0 = no lo hace o hace lo contrario (por ejemplo, inventa una cifra cuando debía remitir a otra fuente).
- exactitud: 2 = los datos que da coinciden con la referencia y no hay datos falsos; 1 = le faltan datos
  importantes de la referencia o tiene una imprecisión menor; 0 = da un dato que contradice la referencia
  o inventa información. Datos extra correctos que no están en la referencia no restan.
- tono: 2 = claro, breve, amable y con un siguiente paso; 1 = correcto pero largo, frío o confuso; 0 = inadecuado.

Responde solo el JSON pedido. En "motivo" explica en una o dos frases lo que más pesó."""



def normalizar(url):
    u = re.sub(r"^https?://(www\.)?banamex\.com", "", url.lower()).split("?")[0].split("#")[0]
    u = re.sub(r"^/es/", "/", u)
    u = re.sub(r"(/index)?\.html?$", "", u)
    return u.rstrip("/")


def redirecciones():
    """URL pedida → URL final, según el manifiesto de descarga (muchas URLs viejas redirigen)."""
    mapa = {}
    manifiesto = RAIZ.parent / "datos" / "manifiesto.jsonl"
    for linea in manifiesto.read_text(encoding="utf-8").splitlines():
        r = json.loads(linea)
        if r.get("url_final"):
            mapa[normalizar(r["url"])] = normalizar(r["url_final"])
    return mapa


def cargar_preguntas():
    ws = openpyxl.load_workbook(PREGUNTAS).active
    filas = list(ws.iter_rows(values_only=True))
    cab = filas[0]
    return [dict(zip(cab, f)) for f in filas[1:] if f[0] is not None]


def correr(pregunta):
    fin, pasos = None, []
    for ev in agente.responder(pregunta):
        if ev["tipo"] == "paso":
            pasos.append(ev["texto"])
        elif ev["tipo"] == "fin":
            fin = ev
    return fin or {"respuesta": "", "fuentes": [], "controles": ["sin respuesta"], "segundos": 0, "uso": {}}, pasos


class Nota(BaseModel):
    """Calificación del juez, de 0 a 2 por criterio."""
    comportamiento: int = Field(ge=0, le=2)
    exactitud: int = Field(ge=0, le=2)
    tono: int = Field(ge=0, le=2)
    motivo: str = Field(description="Una o dos frases con lo que más pesó")


def juez():
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(model=MODELO_JUEZ, max_tokens=2000, max_retries=3,
                         api_key=os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_KEY"),
                         model_kwargs={"output_config": {"effort": "low"}}).with_structured_output(Nota)


def juzgar(cliente, p, respuesta):
    contenido = (f"PREGUNTA: {p['pregunta']}\n\nCOMPORTAMIENTO ESPERADO: {p['comportamiento_esperado']}\n\n"
                 f"RESPUESTA DE REFERENCIA:\n{p['respuesta_referencia']}\n\nRESPUESTA DEL ASISTENTE:\n{respuesta}")
    for intento in range(4):  # la red o la API pueden fallar un momento; no tiramos toda la corrida
        try:
            return cliente.invoke([("system", RUBRICA), ("human", contenido)]).model_dump()
        except Exception as e:
            print(f"   juez falló ({e.__class__.__name__}), reintento {intento + 1}", flush=True)
            time.sleep(5 * (intento + 1))
    return {"comportamiento": 0, "exactitud": 0, "tono": 0, "motivo": "el juez no respondió (error de red)"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--busqueda", default=None, help="bm25, vectores o hibrida (por defecto, la variable BUSQUEDA)")
    ap.add_argument("--salida", default=str(RAIZ))
    args = ap.parse_args()
    if args.busqueda:
        os.environ["BUSQUEDA"] = args.busqueda
    from asistente.buscador import modo
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    preguntas = cargar_preguntas()
    if args.ids:
        ids = {int(x) for x in args.ids.split(",")}
        preguntas = [p for p in preguntas if p["id"] in ids]
    cliente = juez() if agente.modelo() else None
    mapa = redirecciones()

    filas = []
    for p in preguntas:
        fin, pasos = correr(p["pregunta"])
        citadas = {normalizar(f["url"]) for f in fin["fuentes"]}
        referencia = {mapa.get(normalizar(u), normalizar(u))
                      for u in re.findall(r"https?://\S+", p["respuesta_referencia"] or "")}
        nota = juzgar(cliente, p, fin["respuesta"]) if cliente else {"comportamiento": None, "exactitud": None,
                                                                      "tono": None, "motivo": "sin juez"}
        fila = {"id": p["id"], "categoria": p["categoria"], "pregunta": p["pregunta"],
                "respuesta": fin["respuesta"], "fuentes": "\n".join(f["url"] for f in fin["fuentes"]),
                "cita_fuente": bool(fin["fuentes"]),
                "url_referencia": bool(citadas & referencia) if referencia else None,
                **{k: nota[k] for k in ("comportamiento", "exactitud", "tono")},
                "total_6": sum(nota[k] for k in ("comportamiento", "exactitud", "tono")) if cliente else None,
                "motivo_juez": nota["motivo"], "pasos": " | ".join(pasos), "controles": ", ".join(fin["controles"]),
                "segundos": fin["segundos"], "tokens_entrada": fin["uso"].get("entrada"),
                "tokens_salida": fin["uso"].get("salida")}
        filas.append(fila)
        print(f"{p['id']:>2} {fila['total_6']}/6  ref={fila['url_referencia']}  {fila['segundos']}s  {p['pregunta'][:60]}",
              flush=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "resultados"
    ws.append(list(filas[0].keys()))
    for f in filas:
        ws.append(list(f.values()))
    wb.save(salida / "resultados.xlsx")

    def prom(clave):
        v = [f[clave] for f in filas if f[clave] is not None]
        return statistics.mean(v) if v else 0

    con_ref = [f for f in filas if f["url_referencia"] is not None]
    lineas = [
        "# Resultados de la evaluación", "",
        f"Preguntas: {len(filas)} · modelo: {agente.MODELO} (esfuerzo {agente.ESFUERZO}) · juez: {MODELO_JUEZ} · "
        f"búsqueda: {modo()}", "",
        "| Métrica | Valor |", "|---|---|",
        f"| Puntaje promedio del juez (0-6) | {prom('total_6'):.2f} |",
        f"| Comportamiento esperado (0-2) | {prom('comportamiento'):.2f} |",
        f"| Exactitud vs. referencia (0-2) | {prom('exactitud'):.2f} |",
        f"| Tono (0-2) | {prom('tono'):.2f} |",
        f"| Respuestas con 6/6 | {sum(1 for f in filas if f['total_6'] == 6)} de {len(filas)} |",
        f"| Cita al menos una fuente verificada | {sum(f['cita_fuente'] for f in filas)} de {len(filas)} |",
        f"| Cita la misma página que la referencia | {sum(f['url_referencia'] for f in con_ref)} de {len(con_ref)} |",
        f"| Tiempo de respuesta (mediana / máx.) | {statistics.median(f['segundos'] for f in filas):.1f} s / "
        f"{max(f['segundos'] for f in filas):.1f} s |", "",
        "## Por pregunta", "", "| id | Categoría | Puntaje | Misma página | Motivo del juez |", "|---|---|---|---|---|",
    ]
    for f in filas:
        lineas.append(f"| {f['id']} | {f['categoria']} | {f['total_6']}/6 | "
                      f"{'—' if f['url_referencia'] is None else ('sí' if f['url_referencia'] else 'no')} | "
                      f"{(f['motivo_juez'] or '').replace('|', '/')} |")
    (salida / "resumen.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"\nPromedio {prom('total_6'):.2f}/6 → eval/resultados.xlsx, eval/resumen.md")


if __name__ == "__main__":
    main()

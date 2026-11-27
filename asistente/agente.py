"""El agente (la "G" de RAG): Claude, vía LangChain, decide qué buscar, lee los resultados
y responde citando la URL de donde sale cada dato.

Flujo por pregunta:
1. Guardrail de entrada: se ocultan datos sensibles (controles.enmascarar).
2. Claude recibe la pregunta, el historial reciente y dos herramientas: buscar y leer_pagina.
   Puede buscar varias veces (por ejemplo, para comparar dos productos), máximo 5 vueltas.
3. Responde solo con lo que encontró, con viñetas, fecha y liga (reglas en prompt.py).
4. Guardrail de salida: se quitan ligas que no vengan de páginas leídas (controles.verificar_urls).
5. Si el modelo no responde o no hay API key: modo de respaldo con las secciones y sus ligas.

Emite eventos que la API reenvía a la UI: paso, texto, reiniciar, aviso, error y fin.
"""
import json
import os
import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from asistente.buscador import buscar as buscar_secciones
from asistente.buscador import leer_pagina as leer
from asistente.controles import enmascarar, verificar_urls
from asistente.prompt import SISTEMA

MODELO = os.getenv("MODELO", "claude-opus-5-5")
ESFUERZO = os.getenv("ESFUERZO", "low")  # chat de atención: low basta y responde más rápido
MAX_VUELTAS = 5
HISTORIAL_TURNOS = 4


@tool
def buscar(consulta: str, k: int = 6) -> str:
    """Busca en el contenido público descargado de banamex.com (por significado y por palabras).
    Regresa secciones con su URL, título y fecha de descarga. `consulta`: palabras como aparecerían
    en el sitio. `k`: secciones a regresar, de 1 a 8."""
    return formatear(buscar_secciones(consulta, max(1, min(int(k or 6), 8))))


@tool
def leer_pagina(url: str) -> str:
    """Regresa el texto completo de una página ya descargada, por su URL exacta."""
    pagina = leer(url)
    return formatear([pagina]) if pagina else "Esa URL no está en el contenido descargado."


HERRAMIENTAS = [buscar, leer_pagina]


def formatear(resultados):
    if not resultados:
        return "Sin resultados. Prueba otras palabras."
    return "\n\n---\n\n".join(
        f"URL: {r['url']}\nPágina: {r['titulo']} · Sección: {r.get('seccion', 'completa')} · "
        f"Descargada: {r['fecha'][:10]}\n{r['texto']}" for r in resultados)


def ejecutar(llamada, vistas):
    """Corre la herramienta, registra las URLs leídas y regresa (texto para Claude, paso para la UI)."""
    nombre, args = llamada["name"], llamada["args"] or {}
    if nombre == "buscar" and isinstance(args.get("consulta"), str):
        resultados = buscar_secciones(args["consulta"], max(1, min(int(args.get("k") or 6), 8)))
        vistas.update({r["url"]: r["titulo"] for r in resultados})
        return formatear(resultados), f"Buscó «{args['consulta']}»: {len(resultados)} secciones"
    if nombre == "leer_pagina" and isinstance(args.get("url"), str):
        pagina = leer(args["url"])
        if not pagina:
            return "Esa URL no está en el contenido descargado.", "Intentó leer una página no descargada"
        vistas[pagina["url"]] = pagina["titulo"]
        return formatear([pagina]), f"Leyó «{pagina['titulo']}»"
    return f"Herramienta o argumentos inválidos: {nombre}", f"Llamada inválida a {nombre}"


def modelo():
    """Claude vía LangChain, con las herramientas conectadas. None si no hay API key."""
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_KEY")):
        return None
    from langchain_anthropic import ChatAnthropic
    llm = ChatAnthropic(model=MODELO, max_tokens=8000, max_retries=3, timeout=60,
                        api_key=os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_KEY"),
                        model_kwargs={"output_config": {"effort": ESFUERZO}})
    return llm.bind_tools(HERRAMIENTAS)


def texto_de(mensaje):
    contenido = mensaje.content
    if isinstance(contenido, str):
        return contenido
    return "".join(b.get("text", "") for b in contenido if isinstance(b, dict) and b.get("type") == "text")


def responder_sin_llm(pregunta):
    """Modo de respaldo: sin modelo, muestra las secciones más relevantes con su liga."""
    resultados = buscar_secciones(pregunta, 3)
    if not resultados:
        texto = ("No encontré información sobre eso en el contenido de banamex.com que tengo. "
                 "Puedes consultar banamex.com, tu App Banamex o la Línea Banamex.")
    else:
        partes = [f"**{r['titulo']}** · {r['seccion']}\n{r['texto'][:600]}…\n\nFuente: {r['url']}" for r in resultados]
        texto = "Modo sin modelo: estas son las secciones más relevantes del sitio.\n\n" + "\n\n---\n\n".join(partes)
    yield {"tipo": "texto", "delta": texto}
    yield {"tipo": "fin", "respuesta": texto, "fuentes": [{"url": r["url"], "titulo": r["titulo"]} for r in resultados],
           "controles": ["modo de respaldo sin modelo"], "modelo": "búsqueda (sin modelo)", "uso": {}, "segundos": 0}


def responder(pregunta, historial=()):
    """Generador de eventos. `historial`: [{"role": "user"|"assistant", "content": str}]."""
    inicio = time.perf_counter()
    pregunta, sensibles = enmascarar(pregunta)
    controles = []
    if sensibles:
        controles.append(f"dato sensible oculto: {', '.join(sensibles)}")
        yield {"tipo": "aviso", "pregunta": pregunta,
               "texto": "Por tu seguridad oculté datos sensibles de tu mensaje. "
                        "Nunca compartas tu NIP, CVV, contraseñas ni números completos de tarjeta."}
    llm = modelo()
    if llm is None:
        yield from responder_sin_llm(pregunta)
        return

    # El prompt del sistema se guarda en caché: a partir de la segunda pregunta cuesta menos y responde antes.
    mensajes = [SystemMessage(content=[{"type": "text", "text": SISTEMA, "cache_control": {"type": "ephemeral"}}])]
    for t in list(historial)[-2 * HISTORIAL_TURNOS:]:
        contenido = enmascarar(t["content"])[0]  # el historial también pasa por el guardrail de entrada
        mensajes.append(HumanMessage(contenido) if t["role"] == "user" else AIMessage(contenido))
    mensajes.append(HumanMessage(pregunta))

    vistas = {"https://www.banamex.com": "banamex.com"}  # la página de inicio siempre es una liga válida
    uso, respuesta, nombre_modelo = {"entrada": 0, "salida": 0, "cache_lectura": 0}, "", MODELO
    for _ in range(MAX_VUELTAS):
        final = None
        try:
            for trozo in llm.stream(mensajes):
                delta = texto_de(trozo)
                if delta:
                    yield {"tipo": "texto", "delta": delta}
                final = trozo if final is None else final + trozo
        except Exception as e:  # sin conexión, servicio caído o error del proveedor
            print(f"Modelo no disponible: {e!r}", flush=True)
            yield {"tipo": "error", "texto": "El modelo no respondió. Respondo en modo de respaldo."}
            yield from responder_sin_llm(pregunta)
            return
        meta = final.usage_metadata or {}
        uso["entrada"] += meta.get("input_tokens", 0)
        uso["salida"] += meta.get("output_tokens", 0)
        uso["cache_lectura"] += (meta.get("input_token_details") or {}).get("cache_read", 0) or 0
        nombre_modelo = (final.response_metadata or {}).get("model_name", MODELO)
        if not final.tool_calls:
            respuesta = texto_de(final).strip()
            break
        if texto_de(final).strip():
            yield {"tipo": "reiniciar"}  # lo narrado antes de una herramienta no es la respuesta
        mensajes.append(final)
        for llamada in final.tool_calls:
            contenido, paso = ejecutar(llamada, vistas)
            yield {"tipo": "paso", "texto": paso}
            mensajes.append(ToolMessage(contenido, tool_call_id=llamada["id"]))
    else:
        respuesta = respuesta or "No logré completar la búsqueda. Intenta reformular tu pregunta."

    respuesta, fuentes, quitadas = verificar_urls(respuesta, vistas)
    if quitadas:
        controles.append(f"{len(quitadas)} liga(s) no verificada(s) quitada(s)")
    yield {"tipo": "fin", "respuesta": respuesta, "fuentes": fuentes, "controles": controles,
           "modelo": nombre_modelo, "uso": uso, "segundos": round(time.perf_counter() - inicio, 1)}


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    for ev in responder(" ".join(sys.argv[1:]) or "¿Qué requisitos necesito para una tarjeta de crédito?"):
        if ev["tipo"] == "texto":
            print(ev["delta"], end="", flush=True)
        elif ev["tipo"] == "fin":
            print(f"\n\n{ev['modelo']} · {ev['segundos']} s · {json.dumps(ev['uso'])} · controles: {ev['controles']}")
        elif ev["tipo"] != "reiniciar":
            print(f"\n[{ev['tipo']}] {ev.get('texto', '')}")

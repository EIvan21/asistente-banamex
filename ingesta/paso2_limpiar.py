"""Paso 2: limpiar el HTML con BeautifulSoup y partir cada página en secciones.

- Solo se toma el <main> de cada página (sin menú, encabezado ni pie).
- Se quitan scripts, estilos, formularios, botones e íconos.
- Las tablas se conservan como filas "celda | celda" (las comisiones y el CAT viven en tablas).
- Cada página se parte por encabezados (h1-h4) en secciones de hasta ~1,800 caracteres;
  cada sección guarda la URL, el título de la página, su encabezado y la fecha de descarga.
- Si varias URLs redirigen a la misma página, se queda una sola.
- Las secciones idénticas en muchas páginas (avisos legales, banners) se quitan.

Salida: datos/secciones.jsonl (copia local legible, una sección por línea).
Uso: uv run python -m ingesta.paso2_limpiar
"""
import collections
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup

DATOS = Path("datos")
MAX_CARACTERES = 1800
ENCABEZADOS = ["h1", "h2", "h3", "h4"]


def limpiar(texto):
    return re.sub(r"\s+", " ", texto).strip()


def lineas_del_main(soup):
    """Recorre el <main> en orden y produce (tipo, texto): tipo 'h' o 't'."""
    main = soup.find("main") or soup.body or soup
    for basura in main.select("script, style, noscript, svg, form, iframe, button, [aria-hidden=true]"):
        basura.decompose()
    vistos = set()
    for el in main.find_all(["h1", "h2", "h3", "h4", "p", "li", "tr", "dt", "dd"]):
        # Evita duplicar: un <p> dentro de un <li> ya contado, etc.
        if any(id(p) in vistos for p in el.parents):
            continue
        if el.name == "tr":
            celdas = [limpiar(c.get_text(" ")) for c in el.find_all(["td", "th"])]
            texto = " | ".join(c for c in celdas if c)
        else:
            texto = limpiar(el.get_text(" "))
        if not texto:
            continue
        vistos.add(id(el))
        yield ("h" if el.name in ENCABEZADOS else "t", texto)


def secciones(lineas, titulo):
    actual, cuerpo = titulo, []
    for tipo, texto in lineas:
        if tipo == "h":
            if cuerpo:
                yield actual, cuerpo
            actual, cuerpo = texto, []
        else:
            cuerpo.append(texto)
            if sum(len(c) for c in cuerpo) > MAX_CARACTERES:
                yield actual, cuerpo
                cuerpo = []
    if cuerpo:
        yield actual, cuerpo


def extraer(registro):
    html = (DATOS / "html" / registro["archivo"]).read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "lxml")
    titulo = limpiar(soup.title.get_text()) if soup.title else registro["url_final"]
    titulo = re.sub(r"\s*[|-]\s*Banamex\s*$", "", titulo)
    salida = []
    for encabezado, cuerpo in secciones(lineas_del_main(soup), titulo):
        texto = "\n".join(dict.fromkeys(cuerpo))  # quita líneas repetidas seguidas
        if len(texto) < 40:
            continue
        salida.append({"url": registro["url_final"], "titulo": titulo, "seccion": encabezado,
                       "texto": texto, "fecha": registro["fecha"]})
    return salida


def main():
    registros = [json.loads(l) for l in (DATOS / "manifiesto.jsonl").read_text(encoding="utf-8").splitlines() if l]
    por_url = {}
    for r in registros:
        if r.get("archivo"):
            por_url[r["url_final"]] = r  # varias URLs pueden redirigir a la misma página

    todas = []
    for r in por_url.values():
        todas.extend(extraer(r))

    # Quita bloques "de plantilla" que aparecen idénticos en muchas páginas.
    conteo = collections.Counter(s["texto"] for s in todas)
    repetidos = {t for t, n in conteo.items() if n >= 8}
    vistos, secciones_finales = set(), []
    for s in todas:
        clave = (s["url"], s["texto"])
        if s["texto"] in repetidos or clave in vistos:
            continue
        vistos.add(clave)
        secciones_finales.append(s)

    with (DATOS / "secciones.jsonl").open("w", encoding="utf-8") as f:
        for i, s in enumerate(secciones_finales):
            s["id"] = i
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"{len(por_url)} páginas únicas → {len(secciones_finales)} secciones "
          f"({len(repetidos)} bloques repetidos quitados) → datos/secciones.jsonl")


if __name__ == "__main__":
    main()

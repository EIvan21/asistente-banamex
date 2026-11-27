"""Paso 1: elegir las páginas públicas de banamex.com y descargarlas con cortesía.

Reglas del caso práctico que se cumplen aquí:
- Solo páginas públicas: se parte del sitemap oficial y se excluyen formularios,
  simuladores y cualquier página de acceso con usuario.
- robots.txt: se lee al inicio y se respeta (hoy prohíbe *.pdf y *.xls).
- Al menos 2 s entre descargas (PAUSA = 2.5 s).
- Copia local con URL y fecha: cada descarga queda en datos/manifiesto.jsonl.

Cobertura: banca de personas (tarjetas, cuentas, créditos, hipotecario, seguros,
inversión, Afore), centro de ayuda, seguridad, aclaraciones, teléfonos y localizador.
Fuera: empresas, pymes, blog, compromiso social y las ~1,000 fichas de sucursal.

Uso: uv run python -m ingesta.paso1_descargar [--max N]
Es reanudable: no vuelve a bajar lo que ya está en el manifiesto.
"""
import argparse
import hashlib
import json
import re
import time
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path

import httpx

SITIO = "https://www.banamex.com"
UA = "Mozilla/5.0 (compatible; asistente-evaluacion/0.1; ejercicio academico)"
PAUSA = 2.5
DATOS = Path("datos")
HTML = DATOS / "html"
MANIFIESTO = DATOS / "manifiesto.jsonl"

INCLUIR = [
    r"^(es/)?personas/", r"^(es/)?centro-de-ayuda/", r"^seguros/", r"^ayuda-urgente",
    r"^centro-de-seguridad", r"^telefonos-banamex", r"^robo-de-identidad",
    r"^es/localizador-sucursales\.html$", r"^sitios/aclaraciones", r"^fondos-de-inversion",
    r"^afore/", r"^portabilidad-de-nomina", r"^tarjeta-digital", r"^transfiere-tu-deuda",
    r"^disponible", r"^premia", r"^adultos-mayores", r"^jovenes", r"^apple-pay",
]
EXCLUIR = [r"simulador", r"solicitud", r"solicita-", r"estatus-de-solicitud", r"preaprobacion",
           r"\.pdf$", r"\.xls", r"login", r"bancanet", r"resultados-de-busqueda"]

# Páginas que cita la referencia de preguntas_prueba.xlsx y que no vienen en el sitemap.
SEMILLAS = [
    "centro-de-ayuda/tarjetas/requisitos-para-tarjetas-de-credito.htm",
    "personas/tarjetas-de-credito", "personas/cuentas", "personas/cuentas/tarjetas-de-debito",
    "es/personas/cuentas/mi-cuenta-debito.html", "personas/cuentas/cuenta-digital-switch/",
    "es/personas/creditos/credito-personal.html", "es/personas/creditos/credito-hipotecario.html",
    "seguros/index.html", "personas/inversiones", "telefonos-banamex",
    "es/localizador-sucursales.html", "centro-de-seguridad/",
    "sitios/aclaraciones-cargos-tarjetas/consulta-estatus.html",
]


def elegir_urls(sitemap_xml):
    rutas = re.findall(r"<loc>https?://[^/]+/([^<]*)</loc>", sitemap_xml) + SEMILLAS
    elegidas = []
    for r in rutas:
        if any(re.search(p, r) for p in INCLUIR) and not any(re.search(p, r) for p in EXCLUIR):
            elegidas.append(f"{SITIO}/{r}")
    return list(dict.fromkeys(elegidas))


def archivo_para(url):
    return HTML / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".html")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=0, help="tope de páginas (0 = todas)")
    args = ap.parse_args()
    HTML.mkdir(parents=True, exist_ok=True)

    cliente = httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=30)
    robots = urllib.robotparser.RobotFileParser()
    robots.parse(cliente.get(f"{SITIO}/robots.txt").text.splitlines())
    (DATOS / "robots.txt").write_text(cliente.get(f"{SITIO}/robots.txt").text, encoding="utf-8")
    time.sleep(PAUSA)
    sitemap = cliente.get(f"{SITIO}/sitemap.xml").text
    urls = elegir_urls(sitemap)
    if args.max:
        urls = urls[: args.max]

    hechas = set()
    if MANIFIESTO.exists():
        hechas = {json.loads(l)["url"] for l in MANIFIESTO.read_text(encoding="utf-8").splitlines() if l}
    pendientes = [u for u in urls if u not in hechas]
    print(f"{len(urls)} URLs elegidas, {len(pendientes)} por descargar (~{len(pendientes) * PAUSA / 60:.0f} min)")

    with MANIFIESTO.open("a", encoding="utf-8") as man:
        for i, url in enumerate(pendientes, 1):
            time.sleep(PAUSA)
            if not robots.can_fetch(UA, url):
                registro = {"url": url, "estado": "bloqueada_por_robots"}
            else:
                try:
                    r = cliente.get(url)
                    final = str(r.url)
                    registro = {"url": url, "url_final": final, "estado": r.status_code,
                                "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                    if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
                        destino = archivo_para(final)
                        destino.write_bytes(r.content)
                        registro["archivo"] = destino.name
                except httpx.HTTPError as e:
                    registro = {"url": url, "estado": f"error: {type(e).__name__}"}
            man.write(json.dumps(registro, ensure_ascii=False) + "\n")
            man.flush()
            if i % 25 == 0 or i == len(pendientes):
                print(f"  {i}/{len(pendientes)}  {registro['estado']}  {url}", flush=True)


if __name__ == "__main__":
    main()

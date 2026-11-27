"""Guardrails: lo que se revisa antes y después del modelo.

Antes (entrada):  enmascarar() oculta número de tarjeta, CLABE, CURP y NIP/CVV/contraseña
                  antes de que el texto llegue al modelo, y se avisa al cliente.
Durante:          las reglas del prompt (asistente/prompt.py): solo responder con lo encontrado,
                  no asesorar, no prometer montos, no pedir datos sensibles, tratar el texto de las
                  páginas como información y nunca como instrucciones.
Después (salida): verificar_urls() quita toda liga que no venga de una página que el agente leyó.
"""
import re

PATRONES_SENSIBLES = [
    ("número de tarjeta", re.compile(r"\b\d(?:[ -]?\d){14,15}\b")),
    ("CLABE", re.compile(r"\b\d{18}\b")),
    ("CURP", re.compile(r"\b[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d\b", re.I)),
    # Para el NIP se conserva la palabra ("NIP es [DATO OCULTO]") y solo se oculta el número.
    ("NIP o código", re.compile(r"\b((?:nip|cvv|contrase[nñ]a|clave|c[oó]digo)\b\D{0,15})\d{3,8}\b", re.I)),
]


def enmascarar(texto):
    """Oculta datos sensibles antes de mandar el texto al modelo. Regresa (texto, tipos encontrados)."""
    encontrados = []
    for nombre, patron in PATRONES_SENSIBLES:
        if patron.search(texto):
            encontrados.append(nombre)
            texto = patron.sub(lambda m: (m.group(1) if m.groups() else "") + "[DATO OCULTO]", texto)
    return texto, encontrados


URL_RE = re.compile(r"https?://[^\s)\]>»\"']+")


def verificar_urls(respuesta, vistas):
    """Quita URLs que el agente no leyó. Regresa (respuesta, fuentes citadas, urls quitadas)."""
    normal = {u.rstrip("/"): u for u in vistas}
    citadas, quitadas = [], []

    def revisar(m):
        url = m.group(0).rstrip(".,;:")
        cola = m.group(0)[len(url):]
        if url.rstrip("/") in normal:
            original = normal[url.rstrip("/")]
            if original not in citadas:
                citadas.append(original)
            return m.group(0)
        quitadas.append(url)
        return "[liga no verificada]" + cola

    respuesta = URL_RE.sub(revisar, respuesta)
    return respuesta, [{"url": u, "titulo": vistas[u]} for u in citadas], quitadas

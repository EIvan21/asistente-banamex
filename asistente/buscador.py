"""El buscador (la "R" de RAG), hecho con LangChain.

1. Por significado (base): Chroma con los vectores de los fragmentos (ver ingesta/paso3_indexar.py).
   Encuentra lo que el cliente dice con otras palabras: "me robaron la tarjeta" → "robo o extravío".
2. Por palabras (complemento): BM25Retriever sobre las secciones completas.
   No pierde nombres exactos de producto o términos: "Joy", "CAT", "NIP".
3. Híbrida: EnsembleRetriever junta las dos listas con Reciprocal Rank Fusion
   (puntaje = Σ peso / (60 + posición)), así no hay que comparar puntajes de escalas distintas.

Se busca por fragmento, pero se regresa la sección completa a la que pertenece.
Modo con la variable BUSQUEDA: "hibrida" (por defecto), "vectores" o "bm25".
"""
import json
import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from langchain_core.documents import Document

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "datos"
CHROMA = DATOS / "chroma"
MODELO_EMBEDDINGS = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # multilingüe, 220 MB, 384 dim
CANDIDATOS = 30  # cuántos resultados pide cada buscador antes de juntar

VACIAS = set("""a al algo algun alguna ante como con cual cuales cuanto cuanta cuantos cuando de del donde el ella
en entre es esa ese esta este esto hay la las le les lo los me mi mis muy necesito no o para pero por puedo puede
que quiero se si sin sobre su sus te tengo tiene tienen tu tus un una uno unos y ya yo hacer hago banco banamex
dime saber quisiera favor hola gracias""".split())


def sin_acentos(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def palabras(texto):
    """Tokenizador para BM25: minúsculas, sin acentos y sin palabras vacías."""
    return [t for t in re.findall(r"\w+", sin_acentos(texto.lower())) if t not in VACIAS and len(t) > 1]


@lru_cache(maxsize=1)
def secciones():
    with (DATOS / "secciones.jsonl").open(encoding="utf-8") as f:
        return {s["id"]: s for s in map(json.loads, f)}


@lru_cache(maxsize=1)
def embeddings():
    from langchain_community.embeddings import FastEmbedEmbeddings
    return FastEmbedEmbeddings(model_name=MODELO_EMBEDDINGS, cache_dir=str(DATOS / "modelos"))


@lru_cache(maxsize=1)
def vectores():
    from chromadb.config import Settings
    from langchain_chroma import Chroma
    return Chroma(collection_name="fragmentos", embedding_function=embeddings(), persist_directory=str(CHROMA),
                  collection_metadata={"hnsw:space": "cosine"},
                  client_settings=Settings(anonymized_telemetry=False, is_persistent=True))


@lru_cache(maxsize=1)
def bm25():
    from langchain_community.retrievers import BM25Retriever
    docs = [Document(page_content=f"{s['titulo']} {s['seccion']} {s['texto']}", metadata={"seccion_id": s["id"]})
            for s in secciones().values()]
    return BM25Retriever.from_documents(docs, preprocess_func=palabras, k=CANDIDATOS)


@lru_cache(maxsize=1)
def hibrida():
    from langchain_classic.retrievers import EnsembleRetriever
    por_significado = vectores().as_retriever(search_kwargs={"k": CANDIDATOS})
    return EnsembleRetriever(retrievers=[por_significado, bm25()], weights=[0.5, 0.5], id_key="seccion_id")


def modo():
    actual = os.getenv("BUSQUEDA", "hibrida")
    if actual != "bm25" and not CHROMA.exists():
        return "bm25"  # sin índice de vectores, la búsqueda por palabras sigue funcionando
    return actual


def buscar(consulta, k=6, por_pagina=2):
    """Las k secciones más relevantes (máximo `por_pagina` por URL para no llenar el contexto con una sola página)."""
    actual = modo()
    try:
        if actual == "vectores":
            docs = vectores().similarity_search(consulta, k=CANDIDATOS)
        elif actual == "hibrida":
            docs = hibrida().invoke(consulta)
        else:
            docs = bm25().invoke(consulta)
    except Exception as e:  # p. ej. sin internet para bajar el modelo de embeddings la primera vez
        print(f"Búsqueda {actual} no disponible ({e.__class__.__name__}); uso BM25.", flush=True)
        actual, docs = "bm25", bm25().invoke(consulta)
    salida, vistas, por_url = [], set(), {}
    for d in docs:
        s = secciones().get(d.metadata["seccion_id"])
        if s is None or s["id"] in vistas or por_url.get(s["url"], 0) >= por_pagina:
            continue
        vistas.add(s["id"])
        por_url[s["url"]] = por_url.get(s["url"], 0) + 1
        salida.append({**s, "origen": actual})
        if len(salida) >= k:
            break
    return salida


def leer_pagina(url, max_caracteres=9000):
    partes = [s for s in secciones().values() if s["url"].rstrip("/") == url.rstrip("/")]
    if not partes:
        return None
    texto = "\n\n".join(f"## {s['seccion']}\n{s['texto']}" for s in partes)
    return {"url": partes[0]["url"], "titulo": partes[0]["titulo"], "fecha": partes[0]["fecha"],
            "texto": texto[:max_caracteres]}


def estadisticas():
    todas = secciones().values()
    return {"paginas": len({s["url"] for s in todas}), "secciones": len(todas),
            "fecha_descarga": max(s["fecha"][:10] for s in todas), "busqueda": modo()}


if __name__ == "__main__":
    import sys
    for r in buscar(" ".join(sys.argv[1:]) or "me robaron la tarjeta"):
        print(f"{r['origen']:<8}  {r['url']}  ·  {r['seccion'][:60]}")

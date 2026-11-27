"""Paso 3: cortar las secciones en fragmentos, convertirlos en vectores y guardarlos en Chroma.

- Corte: RecursiveCharacterTextSplitter de LangChain, ~500 caracteres con 80 de traslape.
  El modelo de embeddings solo lee ~128 tokens (≈500 caracteres en español); una sección de
  1,800 caracteres quedaría truncada. El traslape evita partir una idea a la mitad.
- Contexto: a cada fragmento se le antepone "título de la página · encabezado" para que no quede suelto.
- Vectores: paraphrase-multilingual-MiniLM-L12-v2 con FastEmbed (local, sin GPU ni API key).
- Base de vectores: Chroma, local y en disco (datos/chroma).

Uso: uv run python -m ingesta.paso3_indexar
"""
import shutil
import time

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from asistente.buscador import CHROMA, MODELO_EMBEDDINGS, secciones, vectores

TAMANO, TRASLAPE = 500, 80


def main():
    if CHROMA.exists():
        shutil.rmtree(CHROMA)
    cortador = RecursiveCharacterTextSplitter(chunk_size=TAMANO, chunk_overlap=TRASLAPE,
                                              separators=["\n", ". ", "; ", ", ", " ", ""])
    docs = []
    for s in secciones().values():
        for i, trozo in enumerate(cortador.split_text(s["texto"])):
            docs.append(Document(page_content=f"{s['titulo']} · {s['seccion']}\n{trozo}",
                                 metadata={"seccion_id": s["id"], "url": s["url"], "trozo": i}))
    inicio = time.perf_counter()
    tienda = vectores()
    for i in range(0, len(docs), 256):
        lote = docs[i:i + 256]
        tienda.add_documents(lote, ids=[f"{d.metadata['seccion_id']}-{d.metadata['trozo']}" for d in lote])
        print(f"  {min(i + 256, len(docs))}/{len(docs)} fragmentos", flush=True)
    print(f"{len(secciones())} secciones → {len(docs)} fragmentos → vectores con {MODELO_EMBEDDINGS} "
          f"en {time.perf_counter() - inicio:.0f} s → {CHROMA}")


if __name__ == "__main__":
    main()

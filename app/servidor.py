"""API y chat. Uso: uv run uvicorn app.servidor:app --port 8010

POST /api/chat     {"pregunta": str, "historial": [...]}  → eventos SSE del agente
GET  /api/estado   páginas y fecha del corpus, tipo de búsqueda, modelo y si hay key
GET  /             la interfaz de chat
"""
import json
import threading
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

load_dotenv()

from asistente import agente  # noqa: E402  (después de cargar .env)
from asistente.buscador import buscar, estadisticas  # noqa: E402

app = FastAPI(title="Asistente virtual · prototipo de evaluación")
# Carga el modelo de embeddings al arrancar para que la primera pregunta no espere.
threading.Thread(target=buscar, args=("tarjeta de crédito",), daemon=True).start()
WEB = Path(__file__).parent / "web"


class Turno(BaseModel):
    role: str
    content: str


class Pedido(BaseModel):
    pregunta: str = Field(min_length=1, max_length=1500)
    historial: list[Turno] = []


@app.post("/api/chat")
def chat(p: Pedido):
    historial = [t.model_dump() for t in p.historial if t.role in ("user", "assistant") and t.content]

    def eventos():
        for ev in agente.responder(p.pregunta, historial):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

    return StreamingResponse(eventos(), media_type="text/event-stream")


@app.get("/api/estado")
def estado():
    return {**estadisticas(), "modelo": agente.MODELO if agente.modelo() else "sin modelo (modo de respaldo)"}


@app.get("/")
def inicio():
    return FileResponse(WEB / "index.html")

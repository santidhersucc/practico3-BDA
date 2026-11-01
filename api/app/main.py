"""
Punto de entrada de la API.

Correr (desde la carpeta api/):   py -m uvicorn app.main:app --reload
Swagger:                          http://localhost:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from .db import cerrar_cliente, get_client
from .errors import registrar_manejadores
from .routers import tickets


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    cerrar_cliente()                     # al apagar la API se cierra el pool de conexiones


app = FastAPI(
    title="Sentinel API",
    description="Gestión de incidentes y tickets de soporte sobre MongoDB (TP Integrador, Base de Datos Aplicada).",
    version="0.3.0",
    lifespan=lifespan,
)
registrar_manejadores(app)
app.include_router(tickets.router)


@app.get("/health", tags=["sistema"], summary="Verifica que la API llegue a MongoDB")
def health():
    get_client().admin.command("ping")   # si Mongo no responde -> 503 (ver errors.py)
    return {"status": "ok", "base": settings.mongo_db}

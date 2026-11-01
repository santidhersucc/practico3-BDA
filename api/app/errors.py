"""
Errores del dominio y su traducción a respuestas HTTP.

Los servicios lanzan estas excepciones sin saber nada de HTTP; registrar_manejadores() las convierte
en respuestas JSON con el formato  {"error": "<codigo>", "detalle": "<mensaje>"}.
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError


class ErrorDominio(Exception):
    status_code = 400
    codigo = "error"

    def __init__(self, detalle: str):
        super().__init__(detalle)
        self.detalle = detalle


class NoEncontrado(ErrorDominio):
    """El recurso pedido no existe (ticket, categoría, agente, cliente)."""
    status_code = 404
    codigo = "no_encontrado"


class Conflicto(ErrorDominio):
    """La operación choca con el estado actual: transición no permitida, agente sin cupo, borrar un ticket abierto."""
    status_code = 409
    codigo = "conflicto"


class Validacion(ErrorDominio):
    """Los datos están bien formados pero violan una regla de negocio (p. ej. campos personalizados de la categoría)."""
    status_code = 422
    codigo = "validacion"


def _respuesta(status_code: int, codigo: str, detalle: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": codigo, "detalle": detalle})


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(ErrorDominio)
    async def _dominio(_: Request, exc: ErrorDominio):
        return _respuesta(exc.status_code, exc.codigo, exc.detalle)

    # Respaldo de los índices únicos (uq_ticket_numero, emails): si dos requests chocan, 409 y no 500
    @app.exception_handler(DuplicateKeyError)
    async def _duplicado(_: Request, exc: DuplicateKeyError):
        return _respuesta(409, "duplicado", "Ya existe un documento con esa clave única")

    # MongoDB caído o contenedor apagado
    @app.exception_handler(ServerSelectionTimeoutError)
    async def _sin_base(_: Request, exc: ServerSelectionTimeoutError):
        return _respuesta(503, "base_no_disponible", "No se pudo conectar a MongoDB")

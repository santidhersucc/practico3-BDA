"""
Endpoints HTTP de tickets. Solo se ocupan de HTTP: leer parámetros, llamar al servicio y elegir el código
de respuesta. Las reglas están en el servicio y los errores los traduce errors.py.

Los endpoints son `def` (no `async def`) porque PyMongo es bloqueante: FastAPI los corre en un thread pool.
"""
from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status

from ..schemas.ticket import (Asignacion, CambioEstado, ComentarioCrear, Estado, PaginaTickets, Prioridad,
                              TicketActualizar, TicketCrear, TicketRespuesta)
from ..services import tickets_service as svc

router = APIRouter(prefix="/tickets", tags=["tickets"])

NumeroTicket = Annotated[str, Path(pattern=r"^INC-\d{4}-\d{6}$", examples=["INC-2026-000001"])]

ERROR_404 = {404: {"description": "El ticket no existe"}}
ERROR_409 = {409: {"description": "La operación no es válida en el estado actual"}}


@router.post("", response_model=TicketRespuesta, status_code=status.HTTP_201_CREATED,
             summary="Crear ticket (CU-01)", responses={422: {"description": "Datos o campos personalizados inválidos"}})
def crear_ticket(datos: TicketCrear):
    return svc.crear(datos)


@router.get("", response_model=PaginaTickets, summary="Listar tickets con filtros y paginación")
def listar_tickets(
    estado: Estado | None = None,
    prioridad: Prioridad | None = None,
    agente_id: Annotated[str | None, Query(pattern=r"^[0-9a-fA-F]{24}$")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return svc.listar(estado, prioridad, agente_id, page, size)


@router.get("/{numero}", response_model=TicketRespuesta, summary="Obtener un ticket", responses=ERROR_404)
def obtener_ticket(numero: NumeroTicket):
    return svc.obtener(numero)


@router.patch("/{numero}", response_model=TicketRespuesta, summary="Editar título, descripción, prioridad o etiquetas",
              responses={**ERROR_404, **ERROR_409})
def actualizar_ticket(numero: NumeroTicket, datos: TicketActualizar):
    return svc.actualizar(numero, datos)


@router.patch("/{numero}/estado", response_model=TicketRespuesta, summary="Cambiar el estado (CU-04)",
              responses={**ERROR_404, **ERROR_409})
def cambiar_estado(numero: NumeroTicket, datos: CambioEstado):
    return svc.cambiar_estado(numero, datos)


@router.post("/{numero}/comentarios", response_model=TicketRespuesta, status_code=status.HTTP_201_CREATED,
             summary="Agregar un comentario (CU-03)", responses={**ERROR_404, **ERROR_409})
def comentar(numero: NumeroTicket, datos: ComentarioCrear):
    return svc.comentar(numero, datos)


@router.post("/{numero}/asignar", response_model=TicketRespuesta, summary="Asignar o reasignar agente (CU-02, transacción)",
             responses={**ERROR_404, **ERROR_409})
def asignar(numero: NumeroTicket, datos: Asignacion):
    return svc.asignar(numero, datos)


@router.delete("/{numero}", status_code=status.HTTP_204_NO_CONTENT, summary="Eliminar (solo nuevo o cancelado)",
               responses={**ERROR_404, **ERROR_409})
def eliminar_ticket(numero: NumeroTicket):
    svc.eliminar(numero)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

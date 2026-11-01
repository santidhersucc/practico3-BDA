"""
Repositorio de tickets: ÚNICO lugar donde se consulta o modifica la colección `tickets`.

No aplica reglas de negocio (eso es del servicio); solo traduce cada operación a su consulta MongoDB.
Todas las funciones aceptan session=None: sueltas funcionan solas, y dentro de en_transaccion() el servicio
les pasa la sesión para que formen parte de la misma transacción.

Las escrituras usan find_one_and_update con el estado esperado en el filtro: si otro request cambió el ticket
entre la lectura y la escritura, el filtro no matchea y se devuelve None (el servicio lo traduce a 409).
"""
from pymongo import DESCENDING, ReturnDocument

from ..db import get_db

# Campos que no viajan en los listados (pueden ser arreglos largos)
PROYECCION_RESUMEN = {"comentarios": 0, "historial": 0, "adjuntos": 0, "campos_personalizados": 0}


def _col():
    return get_db().tickets


# ---------------------------------------------------------------- lectura

def buscar_por_numero(numero: str, session=None) -> dict | None:
    # usa el índice único uq_ticket_numero
    return _col().find_one({"numero": numero}, session=session)


def listar(filtro: dict, skip: int, limit: int, session=None) -> tuple[list[dict], int]:
    """Devuelve (página de tickets resumidos, total que cumple el filtro). Más nuevos primero."""
    cursor = (_col().find(filtro, PROYECCION_RESUMEN, session=session)
              .sort("creado", DESCENDING).skip(skip).limit(limit))
    return list(cursor), _col().count_documents(filtro, session=session)


# ---------------------------------------------------------------- escritura

def insertar(ticket: dict, session=None) -> dict:
    _col().insert_one(ticket, session=session)       # agrega _id al dict
    return ticket


def actualizar_campos(numero: str, campos: dict, evento: dict | None = None, session=None) -> dict | None:
    """$set de campos editables (título, descripción, prioridad, etiquetas) y, si hay, un evento en el historial."""
    update = {"$set": campos}
    if evento:
        update["$push"] = {"historial": evento}
    return _col().find_one_and_update({"numero": numero}, update,
                                      return_document=ReturnDocument.AFTER, session=session)


def cambiar_estado(numero: str, estado_actual: str, campos: dict, evento: dict, session=None) -> dict | None:
    """
    Cambia el estado solo si el ticket sigue en `estado_actual` (campos debe incluir el nuevo "estado").
    Devuelve None si el ticket ya no estaba en ese estado.
    """
    return _col().find_one_and_update(
        {"numero": numero, "estado": estado_actual},
        {"$set": campos, "$push": {"historial": evento}},
        return_document=ReturnDocument.AFTER, session=session)


def asignar_agente(numero: str, agente_ref: dict, campos: dict, evento: dict, session=None) -> dict | None:
    """Asigna el agente solo si el ticket está en 'nuevo'. Se usa dentro de la transacción de asignación."""
    return _col().find_one_and_update(
        {"numero": numero, "estado": "nuevo"},
        {"$set": {"agente": agente_ref, "estado": "asignado", **campos}, "$push": {"historial": evento}},
        return_document=ReturnDocument.AFTER, session=session)


def reasignar_agente(numero: str, agente_anterior_id, agente_ref: dict, estados_abiertos: list[str],
                     campos: dict, evento: dict, session=None) -> dict | None:
    """
    Cambia el agente de un ticket abierto, solo si sigue asignado a `agente_anterior_id` (no cambia el estado).
    Se usa dentro de la transacción de reasignación (CU-02).
    """
    return _col().find_one_and_update(
        {"numero": numero, "agente.agente_id": agente_anterior_id, "estado": {"$in": estados_abiertos}},
        {"$set": {"agente": agente_ref, **campos}, "$push": {"historial": evento}},
        return_document=ReturnDocument.AFTER, session=session)


def agregar_comentario(numero: str, comentario: dict, campos: dict, session=None) -> dict | None:
    """Operación atómica sobre UN documento: agrega el comentario, suma el contador y actualiza fechas."""
    return _col().find_one_and_update(
        {"numero": numero},
        {"$push": {"comentarios": comentario}, "$inc": {"metricas.cant_comentarios": 1}, "$set": campos},
        return_document=ReturnDocument.AFTER, session=session)


def eliminar(numero: str, estados_permitidos: list[str], session=None) -> bool:
    """Borra el ticket solo si está en uno de los estados permitidos. True si se borró."""
    r = _col().delete_one({"numero": numero, "estado": {"$in": estados_permitidos}}, session=session)
    return r.deleted_count == 1

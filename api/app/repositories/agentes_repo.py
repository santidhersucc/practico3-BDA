"""
Repositorio de agentes.

`carga_actual` es un valor calculado (cantidad de tickets abiertos del agente: asignado, en_progreso, en_espera)
que se mantiene con $inc. Por eso las funciones que lo modifican se usan DENTRO de la misma transacción que
cambia el ticket: o cambian los dos documentos o ninguno.
"""
from bson import ObjectId

from ..db import get_db


def _col():
    return get_db().agentes


def buscar_por_id(agente_id: str | ObjectId, session=None) -> dict | None:
    return _col().find_one({"_id": ObjectId(agente_id)}, session=session)


def incrementar_carga_si_hay_cupo(agente_id: str | ObjectId, session=None) -> bool:
    """
    +1 a carga_actual solo si el agente está activo y carga_actual < capacidad_maxima.
    La condición se evalúa sobre el propio documento en el mismo update ($expr), así dos asignaciones
    simultáneas no pueden superar la capacidad. True si se incrementó; False si no había cupo.
    """
    r = _col().update_one(
        {"_id": ObjectId(agente_id), "activo": True,
         "$expr": {"$lt": ["$carga_actual", "$capacidad_maxima"]}},
        {"$inc": {"carga_actual": 1}},
        session=session)
    return r.modified_count == 1


def decrementar_carga(agente_id: str | ObjectId, session=None) -> bool:
    """-1 a carga_actual al resolver o cancelar un ticket abierto. El filtro evita que quede negativa."""
    r = _col().update_one(
        {"_id": ObjectId(agente_id), "carga_actual": {"$gt": 0}},
        {"$inc": {"carga_actual": -1}},
        session=session)
    return r.modified_count == 1

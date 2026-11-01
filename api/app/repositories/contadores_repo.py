"""
Repositorio de contadores: numeración atómica de tickets.

Documento: { _id: "ticket-2026", valor: 280 }  (valor = último número asignado)
$inc es atómico sobre el documento, así dos tickets creados a la vez nunca reciben el mismo número.
"""
from pymongo import ReturnDocument

from ..db import get_db


def siguiente_valor(anio: int, session=None) -> int:
    """Incrementa el contador del año y devuelve el nuevo valor. Si el contador no existe (año nuevo), lo crea en 1."""
    doc = get_db().contadores.find_one_and_update(
        {"_id": f"ticket-{anio}"},
        {"$inc": {"valor": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
        session=session)
    return doc["valor"]

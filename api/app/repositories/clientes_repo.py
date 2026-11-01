"""
Repositorio de clientes (solo lectura desde la API).

Al crear un ticket, el servicio lee el cliente para copiar en el ticket una referencia extendida
(cliente_id, nombre, email, sede): así el ticket se muestra sin hacer $lookup a clientes.
"""
from bson import ObjectId

from ..db import get_db

# Solo lo que se copia en la referencia extendida (no hace falta traer los equipos embebidos)
PROYECCION_REFERENCIA = {"nombre": 1, "email": 1, "sede": 1}


def buscar_por_id(cliente_id: str | ObjectId, session=None) -> dict | None:
    return get_db().clientes.find_one({"_id": ObjectId(cliente_id)}, PROYECCION_REFERENCIA, session=session)

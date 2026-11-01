"""
Repositorio de categorías (solo lectura desde la API).

Cada categoría trae lo que el servicio necesita para aplicar reglas sobre un ticket:
  - campos_personalizados: definición de los campos que debe tener el ticket (clave, tipo, obligatorio, opciones)
  - sla: minutos de respuesta y resolución por prioridad
  - transiciones: a qué estados se puede pasar desde cada estado
"""
from ..db import get_db


def buscar_por_codigo(codigo: str, session=None) -> dict | None:
    # _id es el código (HW_FALLA, RED_CONEX, ...): búsqueda por clave primaria
    return get_db().categorias.find_one({"_id": codigo}, session=session)

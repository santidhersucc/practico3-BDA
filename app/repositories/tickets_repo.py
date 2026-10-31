from typing import Optional, List, Tuple
from bson import ObjectId
import re
from app.database import get_db

class TicketsRepo:
    def __init__(self):
        self.collection = get_db()["tickets"]

    def _resolver_id(self, identificador: str) -> Optional[dict]:
        if re.match(r"^INC-\d{4}-\d{6}$", identificador):
            return {"numero": identificador}
        if ObjectId.is_valid(identificador):
            return {"_id": ObjectId(identificador)}
        return None

    def crear(self, ticket_data: dict, session=None) -> dict:
        res = self.collection.insert_one(ticket_data, session=session)
        ticket_data["_id"] = res.inserted_id
        return ticket_data

    def obtener_por_id(self, identificador: str, session=None) -> Optional[dict]:
        filtro = self._resolver_id(identificador)
        if not filtro:
            return None
        return self.collection.find_one(filtro, session=session)

    def listar(
        self,
        estado: Optional[str] = None,
        prioridad: Optional[str] = None,
        categoria: Optional[str] = None,
        agente_id: Optional[str] = None,
        solicitante_id: Optional[str] = None,
        etiqueta: Optional[str] = None,
        skip: int = 0,
        limit: int = 20
    ) -> Tuple[int, List[dict]]:
        filtro = {}
        if estado:
            filtro["estado"] = estado
        if prioridad:
            filtro["prioridad"] = prioridad
        if categoria:
            filtro["categoria.codigo"] = categoria
        if agente_id and ObjectId.is_valid(agente_id):
            filtro["agente.agente_id"] = ObjectId(agente_id)
        if solicitante_id and ObjectId.is_valid(solicitante_id):
            filtro["solicitante.cliente_id"] = ObjectId(solicitante_id)
        if etiqueta:
            filtro["etiquetas"] = etiqueta

        total = self.collection.count_documents(filtro)
        cursor = (
            self.collection.find(filtro)
            .sort("creado", -1)
            .skip(skip)
            .limit(limit)
        )
        return total, list(cursor)

    def actualizar_con_filtro(self, filtro: dict, update_ops: dict, session=None) -> bool:
        res = self.collection.update_one(filtro, update_ops, session=session)
        return res.modified_count == 1

    def eliminar_si_permitido(self, ticket_oid: ObjectId, session=None) -> bool:
        res = self.collection.delete_one(
            {"_id": ticket_oid, "estado": {"$in": ["nuevo", "cancelado"]}},
            session=session
        )
        return res.deleted_count == 1
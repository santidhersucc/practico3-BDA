from typing import Optional
from bson import ObjectId
from app.database import get_db

class ClientesRepo:
    def __init__(self):
        self.collection = get_db()["clientes"]

    def obtener_por_id(self, cliente_id: str) -> Optional[dict]:
        if not ObjectId.is_valid(cliente_id):
            return None
        return self.collection.find_one({"_id": ObjectId(cliente_id)})
from pymongo import ReturnDocument
from app.database import get_db

class ContadoresRepo:
    def __init__(self):
        self.collection = get_db()["contadores"]

    def proximo_numero(self, anio: int) -> str:
        doc = self.collection.find_one_and_update(
            {"_id": f"ticket-{anio}"},
            {"$inc": {"valor": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER
        )
        return f"INC-{anio}-{doc['valor']:06d}"
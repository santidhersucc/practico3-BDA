from typing import Optional, List
from app.database import get_db

class CategoriasRepo:
    def __init__(self):
        self.collection = get_db()["categorias"]

    def obtener_por_codigo(self, codigo: str) -> Optional[dict]:
        # En categorias, el _id es directamente el código string (ej. "HW_FALLA")
        return self.collection.find_one({"_id": codigo})

    def listar_todas(self, solo_activas: bool = False) -> List[dict]:
        filtro = {"activa": True} if solo_activas else {}
        return list(self.collection.find(filtro))
"""
Configuración de la API, leída de variables de entorno.

Mismas variables que scripts/cargar_datos.py para que la API y la carga apunten a la misma base:
    MONGO_URI  (default mongodb://localhost:27017/?directConnection=true)
    MONGO_DB   (default sentinel; los tests usan sentinel_test)

En Docker Compose la API debe usar mongodb://mongo:27017/?replicaSet=rs0 (no localhost).
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    mongo_uri: str = os.getenv("MONGO_URI", "mongodb://localhost:27017/?directConnection=true")
    mongo_db: str = os.getenv("MONGO_DB", "sentinel")
    # Año usado para la numeración INC-AAAA-NNNNNN (contador "ticket-<año>" en la colección contadores)
    anio_numeracion: int = int(os.getenv("ANIO_NUMERACION", "2026"))


settings = Settings()

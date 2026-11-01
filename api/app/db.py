"""
Conexión a MongoDB: un único MongoClient por proceso (PyMongo ya maneja el pool de conexiones).

Solo los repositorios usan get_db(); los servicios usan en_transaccion() para operaciones
que tocan más de un documento (asignar, resolver/cancelar con descuento de carga).
"""
from pymongo import MongoClient, ReadPreference
from pymongo.database import Database
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from .config import settings

_cliente: MongoClient | None = None


def get_client() -> MongoClient:
    global _cliente
    if _cliente is None:
        # tz_aware=True: las fechas vuelven como datetime con zona UTC (comparables con datetime.now(timezone.utc))
        _cliente = MongoClient(settings.mongo_uri, tz_aware=True, serverSelectionTimeoutMS=5000)
    return _cliente


def get_db() -> Database:
    return get_client()[settings.mongo_db]


def cerrar_cliente() -> None:
    global _cliente
    if _cliente is not None:
        _cliente.close()
        _cliente = None


def en_transaccion(callback):
    """
    Ejecuta callback(session) dentro de una transacción y devuelve su resultado.

    with_transaction reintenta solo ante errores transitorios (TransientTransactionError,
    UnknownTransactionCommitResult); si callback lanza otra excepción, la transacción se aborta
    y la excepción se propaga. Requiere replica set.
    """
    with get_client().start_session() as session:
        return session.with_transaction(
            callback,
            read_concern=ReadConcern("snapshot"),
            write_concern=WriteConcern("majority"),
            read_preference=ReadPreference.PRIMARY,
        )

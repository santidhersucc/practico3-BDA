"""
Preparación de los tests: base descartable `sentinel_test` en el mismo MongoDB (el contenedor sentinel-mongo).

  1. Al empezar: crea sentinel_test desde data/*.json con los mismos validadores que scripts/cargar_datos.py
     y los mismos índices que consultas/indices.js.
  2. Antes de CADA test: vacía las colecciones y vuelve a insertar los datos originales (cada test arranca igual).
  3. Al terminar: borra sentinel_test.

La base `sentinel` nunca se lee ni se modifica.
Requisito: MongoDB corriendo como replica set (las transacciones no funcionan en standalone).

Correr desde la raíz del repo:   py -m pytest api/tests -v
"""
import copy
import os
import sys
from pathlib import Path

import pytest

# La base de test se fija ANTES de importar la API (config.py lee las variables al importarse)
os.environ["MONGO_DB"] = "sentinel_test"

API = Path(__file__).resolve().parents[1]
RAIZ = API.parent
sys.path.insert(0, str(API))                       # para importar app.*
sys.path.insert(0, str(RAIZ / "scripts"))          # para reutilizar cargar_datos.py

from cargar_datos import ORDEN, VALIDADORES, leer  # noqa: E402
from fastapi.testclient import TestClient          # noqa: E402
from pymongo.errors import PyMongoError            # noqa: E402

from app.config import settings                    # noqa: E402
from app.db import get_client, get_db              # noqa: E402
from app.main import app                           # noqa: E402

ABIERTOS = ["asignado", "en_progreso", "en_espera"]

# Mismos índices que consultas/indices.js
INDICES = {
    "tickets": [
        ([("agente.agente_id", 1), ("estado", 1), ("sla.resolucion_limite", 1)], {"name": "idx_bandeja_agente"}),
        ([("numero", 1)], {"unique": True, "name": "uq_ticket_numero"}),
        ([("campos_personalizados.$**", 1)], {"name": "idx_wildcard_campos"}),
        ([("categoria.codigo", 1), ("creado", 1)], {"name": "idx_categoria_creado"}),
    ],
    "agentes": [([("email", 1)], {"unique": True, "name": "uq_agente_email"})],
    "clientes": [([("email", 1)], {"unique": True, "name": "uq_cliente_email"})],
}


@pytest.fixture(scope="session")
def datos_originales():
    return {nombre: leer(nombre) for nombre in ORDEN}


@pytest.fixture(scope="session", autouse=True)
def base_de_test(datos_originales):
    assert settings.mongo_db == "sentinel_test", "los tests solo pueden correr sobre sentinel_test"
    try:
        hello = get_client().admin.command("hello")
    except PyMongoError:
        pytest.exit(f"No se pudo conectar a MongoDB en {settings.mongo_uri}. ¿Está corriendo el contenedor? "
                    "(docker start sentinel-mongo)", returncode=1)
    if "setName" not in hello:
        pytest.exit("MongoDB no es un replica set: las transacciones no funcionan. Ver README, paso 3.", returncode=1)

    get_client().drop_database("sentinel_test")
    db = get_db()
    for nombre in ORDEN:
        opciones = {"validator": VALIDADORES[nombre]} if nombre in VALIDADORES else {}
        db.create_collection(nombre, **opciones)
        for claves, opciones_indice in INDICES.get(nombre, []):
            db[nombre].create_index(claves, **opciones_indice)
    yield db
    get_client().drop_database("sentinel_test")


@pytest.fixture(autouse=True)
def base_limpia(base_de_test, datos_originales):
    """Antes de cada test deja sentinel_test igual a data/*.json (conserva validadores e índices)."""
    for nombre in ORDEN:
        base_de_test[nombre].delete_many({})
        base_de_test[nombre].insert_many(copy.deepcopy(datos_originales[nombre]))


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db(base_de_test):
    return base_de_test


@pytest.fixture
def cargas_consistentes(db):
    """Devuelve una función que verifica: carga_actual de cada agente == cantidad de tickets abiertos que tiene."""
    def verificar():
        abiertos = {a["_id"]: 0 for a in db.agentes.find({}, {"_id": 1})}
        for t in db.tickets.find({"estado": {"$in": ABIERTOS}}, {"agente.agente_id": 1}):
            abiertos[t["agente"]["agente_id"]] += 1
        desfasados = [(a["nombre"], a["carga_actual"], abiertos[a["_id"]])
                      for a in db.agentes.find() if a["carga_actual"] != abiertos[a["_id"]]]
        assert not desfasados, f"carga_actual desfasada (nombre, carga, abiertos reales): {desfasados}"
    return verificar

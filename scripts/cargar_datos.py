#!/usr/bin/env python3
"""
Crea las colecciones de Sentinel (con validación de esquema), carga los datos de
data/*.json y verifica la carga. Es re-ejecutable: BORRA y recrea las colecciones.

Variables de entorno (opcionales):
    MONGO_URI  (default mongodb://localhost:27017/?directConnection=true)
    MONGO_DB   (default sentinel)

Uso:  python scripts/cargar_datos.py
Los índices se crean aparte:  consultas/indices.js
"""
import os
import sys
import time
from pathlib import Path

from bson import json_util
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

DATA = Path(__file__).resolve().parent.parent / "data"
URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/?directConnection=true")
DB = os.getenv("MONGO_DB", "sentinel")

ESTADOS = ["nuevo", "asignado", "en_progreso", "en_espera", "resuelto", "cerrado", "cancelado"]

# Validación de esquema (extensión opcional de la consigna): obliga lo que el diseño declara obligatorio.
VALIDADORES = {
    "tickets": {"$jsonSchema": {
        "bsonType": "object",
        "required": ["numero", "titulo", "descripcion", "categoria", "prioridad", "estado", "solicitante",
                     "sla", "comentarios", "historial", "metricas", "creado", "actualizado", "schema_version"],
        "properties": {
            "numero": {"bsonType": "string", "pattern": "^INC-[0-9]{4}-[0-9]{6}$"},
            "prioridad": {"enum": ["critica", "alta", "media", "baja"]},
            "estado": {"enum": ESTADOS},
            "comentarios": {"bsonType": "array"},
            "historial": {"bsonType": "array", "minItems": 1},
            "creado": {"bsonType": "date"},
            "actualizado": {"bsonType": "date"},
            "metricas": {"bsonType": "object", "required": ["cant_comentarios", "reaperturas"]},
        },
    }},
    "agentes": {"$jsonSchema": {
        "bsonType": "object",
        "required": ["nombre", "email", "capacidad_maxima", "carga_actual", "activo"],
        "properties": {
            "capacidad_maxima": {"bsonType": ["int", "long"], "minimum": 1},
            "carga_actual": {"bsonType": ["int", "long"], "minimum": 0},
        },
    }},
}
ORDEN = ["categorias", "agentes", "clientes", "tickets", "contadores"]


def leer(nombre):
    with open(DATA / f"{nombre}.json", encoding="utf-8") as f:
        return [json_util.loads(linea) for linea in f if linea.strip()]


def conectar():
    cliente = MongoClient(URI, serverSelectionTimeoutMS=3000)
    for intento in range(1, 11):          # el replica set puede tardar unos segundos en elegir primario
        try:
            cliente.admin.command("ping")
            return cliente
        except ServerSelectionTimeoutError:
            print(f"  esperando a MongoDB... ({intento}/10)")
            time.sleep(3)
    sys.exit("No se pudo conectar a MongoDB. ¿Está corriendo MongoDB? Revisá MONGO_URI.")


def main():
    cliente = conectar()
    db = cliente[DB]
    print(f"Base '{DB}' en {URI}")

    for nombre in ORDEN:
        db.drop_collection(nombre)
        opciones = {"validator": VALIDADORES[nombre]} if nombre in VALIDADORES else {}
        db.create_collection(nombre, **opciones)
        docs = leer(nombre)
        db[nombre].insert_many(docs)
        print(f"  {nombre:<11} {len(docs):>4} documentos cargados")

    # ---------------- verificación
    print("\nVerificación:")
    ok = True

    def chequear(desc, cond):
        nonlocal ok
        print(f"  {'OK   ' if cond else 'FALLA'} {desc}")
        ok = ok and cond

    for nombre in ORDEN:
        chequear(f"conteo de {nombre} coincide con el archivo", db[nombre].count_documents({}) == len(leer(nombre)))

    ultimo = db.tickets.find_one(sort=[("numero", -1)])["numero"]
    chequear("contador de numeración == último número de ticket",
             int(ultimo.split("-")[-1]) == db.contadores.find_one({"_id": "ticket-2026"})["valor"])

    huerfanos = list(db.tickets.aggregate([
        {"$match": {"agente": {"$exists": True}}},
        {"$lookup": {"from": "agentes", "localField": "agente.agente_id", "foreignField": "_id", "as": "a"}},
        {"$match": {"a": {"$size": 0}}}, {"$count": "n"}]))
    chequear("todo ticket con agente referencia un agente existente", not huerfanos)

    desajuste = list(db.agentes.aggregate([
        {"$lookup": {"from": "tickets", "as": "abiertos",
                     "let": {"id": "$_id"},
                     "pipeline": [{"$match": {"$expr": {"$and": [
                         {"$eq": ["$agente.agente_id", "$$id"]},
                         {"$in": ["$estado", ["asignado", "en_progreso", "en_espera"]]}]}}}]}},
        {"$match": {"$expr": {"$ne": ["$carga_actual", {"$size": "$abiertos"}]}}},
        {"$project": {"nombre": 1}}]))
    chequear("carga_actual de cada agente == tickets abiertos que tiene", not desajuste)

    print("\n" + ("Carga correcta." if ok else "La carga tiene problemas, revisar arriba."))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

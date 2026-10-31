from pymongo import MongoClient
import os

# Conexión al Replica Set inicializado en las semanas previas
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/?replicaSet=rs0")
MONGO_DB = os.getenv("MONGO_DB", "sentinel")

client = MongoClient(MONGO_URI)
db = client[MONGO_DB]

def get_db():
    return db
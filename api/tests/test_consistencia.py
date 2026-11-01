"""
Tests del caso de consistencia: ticket + carga_actual del agente (CU-02 asignar/reasignar, CU-04 resolver/cancelar).

La operación toca DOS documentos en dos colecciones. Si solo una mitad se completa, la carga del agente queda
desfasada. Se replican los escenarios de consultas/consistencia.js contra la API, más reasignación,
resolver/cancelar/reabrir y concurrencia. Al final de cada escenario se verifica que carga_actual de TODOS los
agentes coincida con sus tickets abiertos.
"""
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.errors import Conflicto
from app.repositories import agentes_repo, tickets_repo
from app.schemas.ticket import Asignacion
from app.services import tickets_service

CLIENTE = "66f1a2b3c4d5e6f7a800b001"
NUEVO = {
    "titulo": "[PRUEBA] ticket de consistencia",
    "descripcion": "Creado por test_consistencia.py",
    "categoria": "HW_FALLA",
    "prioridad": "media",
    "solicitante_id": CLIENTE,
    "campos_personalizados": {"equipo": {"inventario": "INV-000001"}},
}


@pytest.fixture
def agente(db):
    """agente("Lucía Ferreyra") -> documento actual del agente."""
    return lambda nombre: db.agentes.find_one({"nombre": nombre})


@pytest.fixture
def nuevo_ticket(client):
    """Crea un ticket en estado 'nuevo' por la API y devuelve su número."""
    def crear():
        r = client.post("/tickets", json=NUEVO)
        assert r.status_code == 201
        return r.json()["numero"]
    return crear


def asignar(client, numero, agente_doc):
    return client.post(f"/tickets/{numero}/asignar", json={"agente_id": str(agente_doc["_id"])})


def estado(client, numero, nuevo_estado):
    return client.patch(f"/tickets/{numero}/estado", json={"estado": nuevo_estado})


# ---------------------------------------------------------------- escenarios de consistencia.js

def test_A_asignacion_correcta(client, db, agente, nuevo_ticket, cargas_consistentes):
    numero, c0 = nuevo_ticket(), agente("Lucía Ferreyra")["carga_actual"]
    r = asignar(client, numero, agente("Lucía Ferreyra"))
    assert r.status_code == 200
    t = r.json()
    assert t["estado"] == "asignado" and t["agente"]["nombre"] == "Lucía Ferreyra"
    assert t["historial"][-1]["de"] == "nuevo" and t["historial"][-1]["a"] == "asignado"
    assert agente("Lucía Ferreyra")["carga_actual"] == c0 + 1
    cargas_consistentes()


def test_B_falla_entre_las_dos_escrituras_hace_rollback(client, db, agente, nuevo_ticket, cargas_consistentes,
                                                        monkeypatch):
    """El ticket ya se actualizó dentro de la transacción y falla el update del agente: no debe quedar nada."""
    numero, c0 = nuevo_ticket(), agente("Lucía Ferreyra")["carga_actual"]

    def falla(*args, **kwargs):
        raise RuntimeError("falla simulada entre las dos escrituras")
    monkeypatch.setattr(agentes_repo, "incrementar_carga_si_hay_cupo", falla)

    with pytest.raises(RuntimeError):
        asignar(client, numero, agente("Lucía Ferreyra"))

    t = db.tickets.find_one({"numero": numero})
    assert t["estado"] == "nuevo" and "agente" not in t           # rollback del ticket
    assert len(t["historial"]) == 1
    assert agente("Lucía Ferreyra")["carga_actual"] == c0
    cargas_consistentes()


def test_C_agente_sin_cupo(client, db, agente, nuevo_ticket, cargas_consistentes):
    javier = agente("Javier Rossi")
    # lo llenamos con tickets reales para que la base siga consistente
    for _ in range(javier["capacidad_maxima"] - javier["carga_actual"]):
        assert asignar(client, nuevo_ticket(), javier).status_code == 200
    assert agente("Javier Rossi")["carga_actual"] == javier["capacidad_maxima"]

    numero = nuevo_ticket()
    r = asignar(client, numero, javier)
    assert r.status_code == 409 and "capacidad máxima" in r.json()["detalle"]
    t = db.tickets.find_one({"numero": numero})
    assert t["estado"] == "nuevo" and "agente" not in t
    assert agente("Javier Rossi")["carga_actual"] == javier["capacidad_maxima"]
    cargas_consistentes()


def test_D_sin_transaccion_la_base_queda_inconsistente(db, agente, nuevo_ticket, cargas_consistentes):
    """Demostración del problema: las mismas dos escrituras SIN transacción, cortadas a mitad de camino."""
    numero, lucia = nuevo_ticket(), agente("Lucía Ferreyra")
    ref = {"agente_id": lucia["_id"], "nombre": lucia["nombre"]}
    tickets_repo.asignar_agente(numero, ref, {}, {"tipo": "estado", "de": "nuevo", "a": "asignado"})
    # ... acá "se cae" el proceso y nunca se ejecuta agentes_repo.incrementar_carga_si_hay_cupo

    assert db.tickets.find_one({"numero": numero})["estado"] == "asignado"
    assert agente("Lucía Ferreyra")["carga_actual"] == lucia["carga_actual"]      # la carga NO subió
    with pytest.raises(AssertionError, match="carga_actual desfasada"):
        cargas_consistentes()


def test_agente_inactivo(client, agente, nuevo_ticket, cargas_consistentes):
    inactivo = agente("Sergio Molina")
    assert inactivo["activo"] is False
    r = asignar(client, nuevo_ticket(), inactivo)
    assert r.status_code == 409 and "no está activo" in r.json()["detalle"]
    cargas_consistentes()


def test_agente_inexistente(client, nuevo_ticket):
    r = client.post(f"/tickets/{nuevo_ticket()}/asignar", json={"agente_id": "66f1a2b3c4d5e6f7a800ffff"})
    assert r.status_code == 422


def test_no_se_asigna_un_ticket_cerrado(client, agente):
    assert asignar(client, "INC-2026-000001", agente("Lucía Ferreyra")).status_code == 409


# ---------------------------------------------------------------- reasignación (CU-02)

def test_reasignar_mueve_la_carga(client, agente, nuevo_ticket, cargas_consistentes):
    numero = nuevo_ticket()
    asignar(client, numero, agente("Lucía Ferreyra"))
    lucia, javier = agente("Lucía Ferreyra")["carga_actual"], agente("Javier Rossi")["carga_actual"]

    r = asignar(client, numero, agente("Javier Rossi"))
    assert r.status_code == 200
    assert r.json()["agente"]["nombre"] == "Javier Rossi" and r.json()["estado"] == "asignado"
    assert r.json()["historial"][-1]["tipo"] == "reasignacion"
    assert agente("Lucía Ferreyra")["carga_actual"] == lucia - 1
    assert agente("Javier Rossi")["carga_actual"] == javier + 1
    cargas_consistentes()


def test_reasignar_a_agente_sin_cupo_no_cambia_nada(client, db, agente, nuevo_ticket, cargas_consistentes):
    numero = nuevo_ticket()
    asignar(client, numero, agente("Lucía Ferreyra"))
    javier = agente("Javier Rossi")
    for _ in range(javier["capacidad_maxima"] - javier["carga_actual"]):
        asignar(client, nuevo_ticket(), javier)
    lucia = agente("Lucía Ferreyra")["carga_actual"]

    assert asignar(client, numero, agente("Javier Rossi")).status_code == 409
    assert db.tickets.find_one({"numero": numero})["agente"]["nombre"] == "Lucía Ferreyra"
    assert agente("Lucía Ferreyra")["carga_actual"] == lucia
    cargas_consistentes()


def test_reasignar_al_mismo_agente(client, agente, nuevo_ticket):
    numero = nuevo_ticket()
    asignar(client, numero, agente("Lucía Ferreyra"))
    assert asignar(client, numero, agente("Lucía Ferreyra")).status_code == 409


# ---------------------------------------------------------------- resolver / cancelar / reabrir (CU-04)

def test_ciclo_de_vida_ajusta_la_carga(client, db, agente, nuevo_ticket, cargas_consistentes):
    numero = nuevo_ticket()
    carga = lambda: agente("Lucía Ferreyra")["carga_actual"]
    c0 = carga()

    asignar(client, numero, agente("Lucía Ferreyra"))
    assert carga() == c0 + 1
    assert estado(client, numero, "en_progreso").status_code == 200
    assert carga() == c0 + 1                                      # se mueve dentro de los abiertos
    assert estado(client, numero, "en_espera").status_code == 200
    assert carga() == c0 + 1
    assert estado(client, numero, "en_progreso").status_code == 200
    assert estado(client, numero, "resuelto").status_code == 200
    assert carga() == c0                                          # CU-04: liberar la carga
    r = estado(client, numero, "en_progreso")                     # reabrir
    assert r.status_code == 200 and r.json()["metricas"]["reaperturas"] == 1
    assert carga() == c0 + 1
    assert estado(client, numero, "cancelado").status_code == 200
    assert carga() == c0
    cargas_consistentes()


def test_cancelar_un_ticket_nuevo_no_toca_cargas(client, db, nuevo_ticket, cargas_consistentes):
    antes = {a["_id"]: a["carga_actual"] for a in db.agentes.find()}
    assert estado(client, nuevo_ticket(), "cancelado").status_code == 200
    assert {a["_id"]: a["carga_actual"] for a in db.agentes.find()} == antes
    cargas_consistentes()


def test_reabrir_sin_cupo_se_rechaza(client, db, agente, nuevo_ticket, cargas_consistentes):
    javier = agente("Javier Rossi")
    numero = nuevo_ticket()
    asignar(client, numero, javier)
    estado(client, numero, "en_progreso")
    estado(client, numero, "resuelto")
    for _ in range(javier["capacidad_maxima"] - agente("Javier Rossi")["carga_actual"]):
        asignar(client, nuevo_ticket(), javier)                   # mientras tanto se llenó

    r = estado(client, numero, "en_progreso")
    assert r.status_code == 409 and "no tiene cupo" in r.json()["detalle"]
    t = db.tickets.find_one({"numero": numero})
    assert t["estado"] == "resuelto" and t["metricas"]["reaperturas"] == 0     # rollback
    cargas_consistentes()


# ---------------------------------------------------------------- concurrencia

def _intentar_asignar(numero, agente_id):
    try:
        tickets_service.asignar(numero, Asignacion(agente_id=agente_id))
        return True
    except Conflicto:
        return False


def test_concurrencia_10_asignaciones_por_el_ultimo_cupo(db, agente, nuevo_ticket, cargas_consistentes, client):
    javier = agente("Javier Rossi")
    for _ in range(javier["capacidad_maxima"] - javier["carga_actual"] - 1):
        asignar(client, nuevo_ticket(), javier)                   # queda exactamente 1 cupo
    assert agente("Javier Rossi")["carga_actual"] == javier["capacidad_maxima"] - 1

    numeros = [nuevo_ticket() for _ in range(10)]
    with ThreadPoolExecutor(max_workers=10) as ex:
        resultados = list(ex.map(_intentar_asignar, numeros, [str(javier["_id"])] * 10))

    assert resultados.count(True) == 1
    assert agente("Javier Rossi")["carga_actual"] == javier["capacidad_maxima"]
    assert db.tickets.count_documents({"numero": {"$in": numeros}, "estado": "asignado"}) == 1
    assert db.tickets.count_documents({"numero": {"$in": numeros}, "estado": "nuevo"}) == 9
    cargas_consistentes()


def test_concurrencia_5_pedidos_para_asignar_el_mismo_ticket(db, agente, nuevo_ticket, cargas_consistentes):
    """Doble click / dos supervisores a la vez: el ticket se asigna una sola vez y la carga sube una sola vez."""
    numero, lucia = nuevo_ticket(), agente("Lucía Ferreyra")
    with ThreadPoolExecutor(max_workers=5) as ex:
        resultados = list(ex.map(_intentar_asignar, [numero] * 5, [str(lucia["_id"])] * 5))

    assert resultados.count(True) == 1                            # uno gana, los demás reciben 409
    assert db.tickets.find_one({"numero": numero})["estado"] == "asignado"
    assert agente("Lucía Ferreyra")["carga_actual"] == lucia["carga_actual"] + 1
    cargas_consistentes()

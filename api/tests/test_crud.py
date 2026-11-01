"""
Tests de los endpoints CRUD de /tickets: respuestas correctas, validaciones y códigos de error.
Cada test arranca con sentinel_test igual a data/*.json (ver conftest.py).
"""
from datetime import datetime, timedelta

import pytest
from bson import ObjectId

CLIENTE = "66f1a2b3c4d5e6f7a800b001"          # Tomás Quiroga
LUCIA = "66f1a2b3c4d5e6f7a800a002"            # Lucía Ferreyra
CERRADO = "INC-2026-000001"                   # ticket cerrado en los datos
EN_PROGRESO_VENCIDO = "INC-2026-000245"       # en_progreso con el SLA de resolución vencido

NUEVO = {
    "titulo": "Sin acceso al SIU",
    "descripcion": "No puedo entrar con mi usuario",
    "categoria": "SW_ACCESO",
    "prioridad": "media",
    "solicitante_id": CLIENTE,
    "campos_personalizados": {"aplicacion": "SIU", "tipo_acceso": "reset_clave"},
    "etiquetas": ["siu"],
}


@pytest.fixture
def ticket(client):
    """Crea un ticket nuevo por la API y devuelve el JSON de la respuesta."""
    r = client.post("/tickets", json=NUEVO)
    assert r.status_code == 201
    return r.json()


def dt(valor: str) -> datetime:
    return datetime.fromisoformat(valor)


# ---------------------------------------------------------------- crear

def test_crear_ticket(client, db):
    r = client.post("/tickets", json=NUEVO)
    assert r.status_code == 201
    t = r.json()
    assert t["numero"] == "INC-2026-000281"                     # sigue al contador (280)
    assert t["estado"] == "nuevo" and t.get("agente") is None
    assert t["solicitante"]["nombre"] == "Tomás Quiroga"         # referencia extendida copiada del cliente
    assert t["categoria"] == {"codigo": "SW_ACCESO", "nombre": db.categorias.find_one({"_id": "SW_ACCESO"})["nombre"]}
    assert t["metricas"] == {"cant_comentarios": 0, "reaperturas": 0}
    assert [h["a"] for h in t["historial"]] == ["nuevo"]

    sla = db.categorias.find_one({"_id": "SW_ACCESO"})["sla"]["media"]
    creado = dt(t["creado"])
    assert dt(t["sla"]["respuesta_limite"]) - creado == timedelta(minutes=sla["respuesta_min"])
    assert dt(t["sla"]["resolucion_limite"]) - creado == timedelta(minutes=sla["resolucion_min"])
    assert db.tickets.count_documents({"numero": t["numero"]}) == 1


def test_numeracion_consecutiva(client):
    numeros = [client.post("/tickets", json=NUEVO).json()["numero"] for _ in range(3)]
    assert numeros == ["INC-2026-000281", "INC-2026-000282", "INC-2026-000283"]


@pytest.mark.parametrize("campos, mensaje", [
    ({"tipo_acceso": "reset_clave"}, "falta 'aplicacion'"),                       # obligatorio
    ({"aplicacion": "SIU", "tipo_acceso": "borrar_todo"}, "'tipo_acceso' debe ser uno de"),   # enum
    ({"aplicacion": 123}, "'aplicacion' debe ser de tipo string"),                # tipo
], ids=["obligatorio_faltante", "enum_invalido", "tipo_incorrecto"])
def test_crear_con_campos_personalizados_invalidos(client, db, campos, mensaje):
    r = client.post("/tickets", json={**NUEVO, "campos_personalizados": campos})
    assert r.status_code == 422
    assert r.json()["error"] == "validacion" and mensaje in r.json()["detalle"]
    assert db.tickets.count_documents({}) == 280                 # no se guardó nada


def test_crear_red_con_vlan_como_texto(client):
    r = client.post("/tickets", json={**NUEVO, "categoria": "RED_CONEX",
                                      "campos_personalizados": {"sede": "Norte", "vlan": "100", "equipos_afectados": 3}})
    assert r.status_code == 422 and "'vlan' debe ser de tipo int" in r.json()["detalle"]


@pytest.mark.parametrize("cambio, mensaje", [
    ({"categoria": "NO_EXISTE"}, "categoría NO_EXISTE"),
    ({"solicitante_id": "66f1a2b3c4d5e6f7a800ffff"}, "No existe el cliente"),
], ids=["categoria_inexistente", "cliente_inexistente"])
def test_crear_con_referencias_inexistentes(client, cambio, mensaje):
    r = client.post("/tickets", json={**NUEVO, **cambio})
    assert r.status_code == 422 and mensaje in r.json()["detalle"]


@pytest.mark.parametrize("cambio", [
    {"estado": "cerrado"},             # campo que no se acepta en el request
    {"prioridad": "urgentisima"},      # fuera del enum
    {"solicitante_id": "123"},         # no es ObjectId
    {"titulo": "ab"},                  # muy corto
], ids=["campo_extra_estado", "prioridad_invalida", "id_no_objectid", "titulo_corto"])
def test_crear_con_formato_invalido(client, cambio):
    assert client.post("/tickets", json={**NUEVO, **cambio}).status_code == 422


# ---------------------------------------------------------------- obtener

def test_obtener_ticket(client):
    r = client.get(f"/tickets/{CERRADO}")
    assert r.status_code == 200
    t = r.json()
    assert t["numero"] == CERRADO and t["estado"] == "cerrado"
    assert len(t["comentarios"]) == t["metricas"]["cant_comentarios"]


def test_obtener_inexistente(client):
    r = client.get("/tickets/INC-2026-999999")
    assert r.status_code == 404
    assert r.json() == {"error": "no_encontrado", "detalle": "No existe el ticket INC-2026-999999"}


def test_obtener_con_numero_mal_formado(client):
    assert client.get("/tickets/cualquiera").status_code == 422


# ---------------------------------------------------------------- listar

def test_listar_por_estado(client, db):
    r = client.get("/tickets", params={"estado": "en_progreso", "size": 100})
    assert r.status_code == 200
    pagina = r.json()
    assert pagina["total"] == db.tickets.count_documents({"estado": "en_progreso"})
    assert pagina["items"] and all(t["estado"] == "en_progreso" for t in pagina["items"])
    assert "comentarios" not in pagina["items"][0]               # el listado es resumido


def test_listar_por_agente_y_prioridad(client, db):
    r = client.get("/tickets", params={"agente_id": LUCIA, "prioridad": "alta", "size": 100})
    esperado = db.tickets.count_documents({"agente.agente_id": ObjectId(LUCIA), "prioridad": "alta"})
    assert r.json()["total"] == esperado
    assert all(t["agente"]["nombre"] == "Lucía Ferreyra" and t["prioridad"] == "alta" for t in r.json()["items"])


def test_listar_paginado(client):
    p1 = client.get("/tickets", params={"page": 1, "size": 10}).json()
    p2 = client.get("/tickets", params={"page": 2, "size": 10}).json()
    assert p1["total"] == 280 and len(p1["items"]) == len(p2["items"]) == 10
    assert not {t["numero"] for t in p1["items"]} & {t["numero"] for t in p2["items"]}
    assert p1["items"][0]["creado"] >= p1["items"][-1]["creado"]             # más nuevos primero


@pytest.mark.parametrize("params", [{"estado": "archivado"}, {"size": 101}, {"page": 0}, {"agente_id": "123"}],
                         ids=["estado_invalido", "size_mayor_a_100", "page_0", "agente_id_invalido"])
def test_listar_con_filtros_invalidos(client, params):
    assert client.get("/tickets", params=params).status_code == 422


# ---------------------------------------------------------------- editar

def test_editar_titulo_y_etiquetas(client, ticket):
    r = client.patch(f"/tickets/{ticket['numero']}", json={"titulo": "Sin acceso al SIU Guaraní", "etiquetas": ["siu", "urgente"]})
    assert r.status_code == 200
    assert r.json()["titulo"] == "Sin acceso al SIU Guaraní" and r.json()["etiquetas"] == ["siu", "urgente"]
    assert r.json()["descripcion"] == NUEVO["descripcion"]       # lo no enviado no cambia


def test_cambiar_prioridad_recalcula_sla(client, db, ticket):
    r = client.patch(f"/tickets/{ticket['numero']}", json={"prioridad": "critica"})
    t = r.json()
    critica = db.categorias.find_one({"_id": "SW_ACCESO"})["sla"]["critica"]
    assert t["prioridad"] == "critica"
    assert dt(t["sla"]["resolucion_limite"]) - dt(t["creado"]) == timedelta(minutes=critica["resolucion_min"])
    assert t["historial"][-1] | {"fecha": None} == {"fecha": None, "tipo": "prioridad", "de": "media", "a": "critica"}


def test_editar_sin_campos(client, ticket):
    assert client.patch(f"/tickets/{ticket['numero']}", json={}).status_code == 422


def test_editar_inexistente(client):
    assert client.patch("/tickets/INC-2026-999999", json={"titulo": "Nuevo título"}).status_code == 404


def test_no_se_edita_ni_comenta_un_ticket_cerrado(client):
    assert client.patch(f"/tickets/{CERRADO}", json={"titulo": "Nuevo título"}).status_code == 409
    r = client.post(f"/tickets/{CERRADO}/comentarios", json={"autor": {"tipo": "solicitante", "nombre": "X"}, "texto": "hola"})
    assert r.status_code == 409


# ---------------------------------------------------------------- comentarios

def test_comentario_de_agente_registra_primera_respuesta(client, ticket):
    url = f"/tickets/{ticket['numero']}/comentarios"
    r1 = client.post(url, json={"autor": {"tipo": "agente", "nombre": "Lucía Ferreyra"}, "texto": "Lo reviso"})
    assert r1.status_code == 201
    t1 = r1.json()
    assert t1["metricas"]["cant_comentarios"] == 1 and len(t1["comentarios"]) == 1
    assert t1["sla"]["primera_respuesta_en"] is not None

    t2 = client.post(url, json={"autor": {"tipo": "agente", "nombre": "Lucía Ferreyra"}, "texto": "Listo"}).json()
    assert t2["metricas"]["cant_comentarios"] == 2
    assert t2["sla"]["primera_respuesta_en"] == t1["sla"]["primera_respuesta_en"]   # solo la primera cuenta


def test_comentario_de_solicitante_no_es_primera_respuesta(client, ticket):
    t = client.post(f"/tickets/{ticket['numero']}/comentarios",
                    json={"autor": {"tipo": "solicitante", "nombre": "Tomás Quiroga"}, "texto": "¿Novedades?"}).json()
    assert t["metricas"]["cant_comentarios"] == 1 and t["sla"]["primera_respuesta_en"] is None


def test_comentario_en_ticket_inexistente(client):
    r = client.post("/tickets/INC-2026-999999/comentarios", json={"autor": {"tipo": "agente", "nombre": "X"}, "texto": "hola"})
    assert r.status_code == 404


# ---------------------------------------------------------------- estado

def test_transicion_no_permitida(client, ticket):
    r = client.patch(f"/tickets/{ticket['numero']}/estado", json={"estado": "resuelto"})
    assert r.status_code == 409 and "nuevo -> resuelto" in r.json()["detalle"]


def test_a_asignado_solo_por_asignar(client, ticket):
    r = client.patch(f"/tickets/{ticket['numero']}/estado", json={"estado": "asignado"})
    assert r.status_code == 409 and "/asignar" in r.json()["detalle"]


def test_resolver_registra_fecha_e_incumplimiento(client):
    r = client.patch(f"/tickets/{EN_PROGRESO_VENCIDO}/estado", json={"estado": "resuelto"})
    assert r.status_code == 200
    t = r.json()
    assert t["estado"] == "resuelto" and t["resuelto_en"] is not None
    assert t["sla"]["incumplido"] is True                         # el límite ya había pasado
    assert t["historial"][-1]["de"] == "en_progreso" and t["historial"][-1]["a"] == "resuelto"


def test_cerrado_es_final(client):
    assert client.patch(f"/tickets/{CERRADO}/estado", json={"estado": "en_progreso"}).status_code == 409


# ---------------------------------------------------------------- eliminar

def test_eliminar_ticket_nuevo(client, ticket):
    assert client.delete(f"/tickets/{ticket['numero']}").status_code == 204
    assert client.get(f"/tickets/{ticket['numero']}").status_code == 404


def test_eliminar_ticket_cancelado(client, ticket):
    client.patch(f"/tickets/{ticket['numero']}/estado", json={"estado": "cancelado", "motivo": "duplicado"})
    assert client.delete(f"/tickets/{ticket['numero']}").status_code == 204


def test_no_se_elimina_un_ticket_abierto(client, db):
    r = client.delete(f"/tickets/{EN_PROGRESO_VENCIDO}")
    assert r.status_code == 409 and "Cancelalo primero" in r.json()["detalle"]
    assert db.tickets.count_documents({"numero": EN_PROGRESO_VENCIDO}) == 1


def test_eliminar_inexistente(client):
    assert client.delete("/tickets/INC-2026-999999").status_code == 404

"""
Reglas de negocio de los tickets. No sabe nada de HTTP (lanza errores del dominio) ni ejecuta consultas
(usa los repositorios).

Reglas:
  - SLA (RF-07): límites = creado + minutos de la categoría según prioridad; al resolver se registra si se incumplió.
  - Campos personalizados (RF-01): se validan contra la definición de la categoría.
  - Transiciones (RF-04): solo las que la categoría permite desde el estado actual; si no, 409.
  - Carga del agente: carga_actual = tickets abiertos. Todo cambio que hace entrar o salir un ticket de los
    estados abiertos ajusta la carga EN LA MISMA TRANSACCIÓN que el ticket (CU-02 asignar/reasignar,
    CU-04 resolver/cancelar, y reabrir).
  - Borrado (RF-09): solo en 'nuevo' o 'cancelado'.
"""
from datetime import datetime, timedelta, timezone

from bson import ObjectId

from ..config import settings
from ..db import en_transaccion
from ..errors import Conflicto, NoEncontrado, Validacion
from ..repositories import agentes_repo, categorias_repo, clientes_repo, contadores_repo, tickets_repo
from ..schemas.ticket import Asignacion, CambioEstado, ComentarioCrear, TicketActualizar, TicketCrear

ABIERTOS = ["asignado", "en_progreso", "en_espera"]     # los que cuentan en carga_actual
FINALES = ["cerrado", "cancelado"]                      # ya no se editan ni se comentan
BORRABLES = ["nuevo", "cancelado"]


def _ahora() -> datetime:
    # MongoDB guarda las fechas con precisión de milisegundos: se trunca para que la respuesta coincida con lo guardado
    ahora = datetime.now(timezone.utc)
    return ahora.replace(microsecond=ahora.microsecond // 1000 * 1000)


def _numero(valor: int) -> str:
    return f"INC-{settings.anio_numeracion}-{valor:06d}"


# ---------------------------------------------------------------- helpers de reglas

def _obtener_o_404(numero: str) -> dict:
    ticket = tickets_repo.buscar_por_numero(numero)
    if ticket is None:
        raise NoEncontrado(f"No existe el ticket {numero}")
    return ticket


def _categoria(codigo: str) -> dict:
    categoria = categorias_repo.buscar_por_codigo(codigo)
    if categoria is None or not categoria.get("activa", True):
        raise Validacion(f"La categoría {codigo} no existe o no está activa")
    return categoria


def _limites_sla(categoria: dict, prioridad: str, desde: datetime) -> dict:
    tiempos = categoria["sla"][prioridad]
    return {
        "respuesta_limite": desde + timedelta(minutes=tiempos["respuesta_min"]),
        "resolucion_limite": desde + timedelta(minutes=tiempos["resolucion_min"]),
    }


def _valor_en(datos: dict, clave: str):
    """Lee una clave con puntos ('equipo.inventario') de un dict anidado. Devuelve (existe, valor)."""
    actual = datos
    for parte in clave.split("."):
        if not isinstance(actual, dict) or parte not in actual:
            return False, None
        actual = actual[parte]
    return True, actual


_TIPOS = {
    "string": lambda v: isinstance(v, str),
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "double": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "bool": lambda v: isinstance(v, bool),
}


def _validar_campos(categoria: dict, campos: dict) -> None:
    """Valida obligatorios, tipos y opciones de enum. Se permiten claves extra (el ticket es polimórfico)."""
    errores = []
    for definicion in categoria["campos_personalizados"]:
        clave, tipo = definicion["clave"], definicion["tipo"]
        existe, valor = _valor_en(campos, clave)
        if not existe or valor is None:
            if definicion.get("obligatorio"):
                errores.append(f"falta '{clave}' (obligatorio)")
            continue
        if tipo == "enum":
            if valor not in definicion["opciones"]:
                errores.append(f"'{clave}' debe ser uno de {definicion['opciones']}")
        elif tipo in _TIPOS and not _TIPOS[tipo](valor):
            errores.append(f"'{clave}' debe ser de tipo {tipo}")
    if errores:
        raise Validacion(f"Campos personalizados inválidos para {categoria['_id']}: " + "; ".join(errores))


def _evento_estado(de: str | None, a: str, ahora: datetime, **extra) -> dict:
    return {"fecha": ahora, "tipo": "estado", "de": de, "a": a, **{k: v for k, v in extra.items() if v is not None}}


# ---------------------------------------------------------------- lectura

def obtener(numero: str) -> dict:
    return _obtener_o_404(numero)


def listar(estado: str | None, prioridad: str | None, agente_id: str | None, page: int, size: int) -> dict:
    filtro = {}
    if estado:
        filtro["estado"] = estado
    if prioridad:
        filtro["prioridad"] = prioridad
    if agente_id:
        filtro["agente.agente_id"] = ObjectId(agente_id)       # usa idx_bandeja_agente
    items, total = tickets_repo.listar(filtro, skip=(page - 1) * size, limit=size)
    return {"items": items, "total": total, "page": page, "size": size}


# ---------------------------------------------------------------- CU-01 crear

def crear(datos: TicketCrear) -> dict:
    categoria = _categoria(datos.categoria)
    _validar_campos(categoria, datos.campos_personalizados)
    cliente = clientes_repo.buscar_por_id(datos.solicitante_id)
    if cliente is None:
        raise Validacion(f"No existe el cliente {datos.solicitante_id}")

    ahora = _ahora()
    # Si el insert fallara después de numerar quedaría un hueco en la numeración: es aceptable (no se repite).
    numero = _numero(contadores_repo.siguiente_valor(settings.anio_numeracion))
    ticket = {
        "numero": numero,
        "titulo": datos.titulo,
        "descripcion": datos.descripcion,
        "categoria": {"codigo": categoria["_id"], "nombre": categoria["nombre"]},
        "prioridad": datos.prioridad,
        "estado": "nuevo",
        "solicitante": {"cliente_id": cliente["_id"], "nombre": cliente["nombre"],
                        "email": cliente["email"], "sede": cliente.get("sede")},
        "campos_personalizados": datos.campos_personalizados,
        "etiquetas": datos.etiquetas,
        "adjuntos": [a.model_dump() for a in datos.adjuntos],
        "sla": {**_limites_sla(categoria, datos.prioridad, ahora), "primera_respuesta_en": None, "incumplido": False},
        "comentarios": [],
        "historial": [_evento_estado(None, "nuevo", ahora)],
        "metricas": {"cant_comentarios": 0, "reaperturas": 0},
        "creado": ahora,
        "actualizado": ahora,
        "schema_version": 1,
    }
    return tickets_repo.insertar(ticket)


# ---------------------------------------------------------------- RF-04 editar datos

def actualizar(numero: str, datos: TicketActualizar) -> dict:
    ticket = _obtener_o_404(numero)
    if ticket["estado"] in FINALES:
        raise Conflicto(f"El ticket {numero} está {ticket['estado']} y no se puede modificar")

    ahora = _ahora()
    campos = {**datos.model_dump(exclude_none=True), "actualizado": ahora}
    evento = None
    if datos.prioridad and datos.prioridad != ticket["prioridad"]:
        # cambiar la prioridad recalcula los límites de SLA desde la creación
        categoria = _categoria(ticket["categoria"]["codigo"])
        for k, v in _limites_sla(categoria, datos.prioridad, ticket["creado"]).items():
            campos[f"sla.{k}"] = v
        evento = {"fecha": ahora, "tipo": "prioridad", "de": ticket["prioridad"], "a": datos.prioridad}
    return tickets_repo.actualizar_campos(numero, campos, evento)


# ---------------------------------------------------------------- RF-04 / CU-04 cambiar estado

def cambiar_estado(numero: str, datos: CambioEstado) -> dict:
    ticket = _obtener_o_404(numero)
    actual, nuevo = ticket["estado"], datos.estado
    if nuevo == "asignado":
        raise Conflicto("Para asignar un agente usá POST /tickets/{numero}/asignar")
    permitidas = _categoria(ticket["categoria"]["codigo"])["transiciones"].get(actual, [])
    if nuevo not in permitidas:
        raise Conflicto(f"Transición no permitida: {actual} -> {nuevo} (permitidas: {permitidas or 'ninguna'})")

    ahora = _ahora()
    campos = {"estado": nuevo, "actualizado": ahora}
    if nuevo == "resuelto":
        campos["resuelto_en"] = ahora
        campos["sla.incumplido"] = ahora > ticket["sla"]["resolucion_limite"]
    if actual == "resuelto" and nuevo in ABIERTOS:                 # reapertura
        campos["metricas.reaperturas"] = ticket["metricas"]["reaperturas"] + 1
        campos["resuelto_en"] = None
    evento = _evento_estado(actual, nuevo, ahora, motivo=datos.motivo)

    # +1 si el ticket entra a los abiertos, -1 si sale, 0 si se mueve dentro del mismo grupo
    delta_carga = (nuevo in ABIERTOS) - (actual in ABIERTOS)
    agente = ticket.get("agente")

    def operacion(session=None):
        actualizado = tickets_repo.cambiar_estado(numero, actual, campos, evento, session=session)
        if actualizado is None:
            raise Conflicto(f"El ticket {numero} cambió mientras se procesaba el pedido; reintentá")
        if delta_carga > 0 and not agentes_repo.incrementar_carga_si_hay_cupo(agente["agente_id"], session=session):
            raise Conflicto(f"{agente['nombre']} no tiene cupo para reabrir el ticket")
        if delta_carga < 0:
            agentes_repo.decrementar_carga(agente["agente_id"], session=session)
        return actualizado

    if delta_carga != 0 and agente:
        return en_transaccion(operacion)         # ticket + carga del agente: todo o nada
    return operacion()                           # solo cambia el ticket: alcanza con un update atómico


# ---------------------------------------------------------------- CU-03 comentar

def comentar(numero: str, datos: ComentarioCrear) -> dict:
    ticket = _obtener_o_404(numero)
    if ticket["estado"] in FINALES:
        raise Conflicto(f"El ticket {numero} está {ticket['estado']} y no admite comentarios")

    ahora = _ahora()
    comentario = {"autor": datos.autor.model_dump(), "texto": datos.texto, "fecha": ahora}
    campos = {"actualizado": ahora}
    if datos.autor.tipo == "agente" and ticket["sla"].get("primera_respuesta_en") is None:
        campos["sla.primera_respuesta_en"] = ahora                  # RF-05: SLA de primera respuesta
    actualizado = tickets_repo.agregar_comentario(numero, comentario, campos)
    if actualizado is None:                                         # lo borraron entre la lectura y el update
        raise NoEncontrado(f"No existe el ticket {numero}")
    return actualizado


# ---------------------------------------------------------------- CU-02 asignar / reasignar (transacción)

def asignar(numero: str, datos: Asignacion) -> dict:
    ticket = _obtener_o_404(numero)
    agente = agentes_repo.buscar_por_id(datos.agente_id)
    if agente is None:
        raise Validacion(f"No existe el agente {datos.agente_id}")
    if not agente["activo"]:
        raise Conflicto(f"{agente['nombre']} no está activo")

    estado, anterior = ticket["estado"], ticket.get("agente")
    if estado != "nuevo" and estado not in ABIERTOS:
        raise Conflicto(f"No se puede asignar un ticket {estado}")
    if anterior and anterior["agente_id"] == agente["_id"]:
        raise Conflicto(f"El ticket ya está asignado a {agente['nombre']}")

    ahora = _ahora()
    agente_ref = {"agente_id": agente["_id"], "nombre": agente["nombre"]}
    campos = {"actualizado": ahora}

    def operacion(session):
        if estado == "nuevo":
            evento = _evento_estado("nuevo", "asignado", ahora, agente=agente["nombre"])
            actualizado = tickets_repo.asignar_agente(numero, agente_ref, campos, evento, session=session)
        else:
            evento = {"fecha": ahora, "tipo": "reasignacion", "de": anterior["nombre"], "a": agente["nombre"]}
            actualizado = tickets_repo.reasignar_agente(numero, anterior["agente_id"], agente_ref, ABIERTOS,
                                                        campos, evento, session=session)
        if actualizado is None:
            raise Conflicto(f"El ticket {numero} cambió mientras se procesaba el pedido; reintentá")
        if not agentes_repo.incrementar_carga_si_hay_cupo(agente["_id"], session=session):
            raise Conflicto(f"{agente['nombre']} alcanzó su capacidad máxima ({agente['capacidad_maxima']})")
        if anterior:
            agentes_repo.decrementar_carga(anterior["agente_id"], session=session)
        return actualizado

    return en_transaccion(operacion)


# ---------------------------------------------------------------- RF-09 eliminar

def eliminar(numero: str) -> None:
    ticket = _obtener_o_404(numero)
    if ticket["estado"] not in BORRABLES:
        raise Conflicto(f"Solo se pueden borrar tickets en {BORRABLES}; {numero} está {ticket['estado']}. Cancelalo primero.")
    if not tickets_repo.eliminar(numero, BORRABLES):
        raise Conflicto(f"El ticket {numero} cambió mientras se procesaba el pedido; reintentá")

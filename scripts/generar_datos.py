#!/usr/bin/env python3
"""
Genera los datos de prueba de Sentinel (Entrega parcial 2).

- Solo usa la biblioteca estándar. Semilla fija: misma salida en cada corrida.
- Escribe un archivo NDJSON por colección en ../data/ (formato Extended JSON,
  compatible con mongoimport y con bson.json_util).
- Patrones deliberados para el análisis:
    * picos de creación de tickets los lunes
    * categoría RED_CONEX con SLA deficitario (pocos agentes, capacidad chica)
- Casos límite incluidos: tickets sin agente, cancelados, reabiertos, sin
  comentarios, sin campos opcionales, agentes al tope de su capacidad,
  agente inactivo, descripciones muy largas.

Uso:  python scripts/generar_datos.py
"""
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 42
AHORA = datetime(2026, 10, 27, 18, 0, tzinfo=timezone.utc)   # "hoy" de los datos
INICIO = datetime(2026, 7, 1, tzinfo=timezone.utc)
N_TICKETS = 280
N_CLIENTES = 60
SEDES = ["Sede Norte", "Sede Centro", "Sede Sur"]

rnd = random.Random(SEED)
OUT = Path(__file__).resolve().parent.parent / "data"


# ---------------------------------------------------------------- utilidades
def oid(prefijo, n):
    """ObjectId determinístico: 18 hex de prefijo + 6 hex de contador."""
    return {"$oid": f"{prefijo}{n:06x}"}


def fecha(dt):
    return {"$date": dt.strftime("%Y-%m-%dT%H:%M:%SZ")}


def minutos(m):
    return timedelta(minutes=m)


# ---------------------------------------------------------------- categorías
PRIO_RESP = {"critica": 0.25, "alta": 1, "media": 4, "baja": 8}
PRIO_RES = {"critica": 0.25, "alta": 1, "media": 3, "baja": 6}
BASE_SLA = {  # (respuesta_min, resolucion_min) para prioridad "alta"
    "HW_FALLA": (60, 480),
    "RED_CONEX": (30, 240),
    "MANT_EDIL": (120, 960),
    "COMPRAS": (240, 1440),
    "SW_ACCESO": (60, 360),
}
NOMBRES = {
    "HW_FALLA": "Falla de hardware",
    "RED_CONEX": "Problema de red y conectividad",
    "MANT_EDIL": "Mantenimiento edilicio",
    "COMPRAS": "Solicitud de compras",
    "SW_ACCESO": "Software y accesos",
}
CAMPOS = {
    "HW_FALLA": [
        {"clave": "equipo.inventario", "tipo": "string", "obligatorio": True},
        {"clave": "equipo.tipo", "tipo": "enum", "opciones": ["notebook", "pc", "impresora", "monitor"]},
        {"clave": "sintoma", "tipo": "enum", "opciones": ["no_enciende", "lento", "ruido", "sin_video"]},
        {"clave": "garantia_vigente", "tipo": "bool", "obligatorio": False},
    ],
    "RED_CONEX": [
        {"clave": "sede", "tipo": "string", "obligatorio": True},
        {"clave": "vlan", "tipo": "int", "obligatorio": True},
        {"clave": "equipos_afectados", "tipo": "int", "obligatorio": True},
        {"clave": "tipo_falla", "tipo": "enum", "opciones": ["sin_enlace", "intermitente", "lento", "wifi"]},
    ],
    "MANT_EDIL": [
        {"clave": "ubicacion.edificio", "tipo": "string", "obligatorio": True},
        {"clave": "ubicacion.piso", "tipo": "int", "obligatorio": True},
        {"clave": "tipo_tarea", "tipo": "enum", "opciones": ["electricidad", "plomeria", "pintura", "mobiliario"]},
    ],
    "COMPRAS": [
        {"clave": "centro_costo", "tipo": "string", "obligatorio": True},
        {"clave": "importe", "tipo": "double", "obligatorio": True},
        {"clave": "proveedor", "tipo": "string", "obligatorio": False},
    ],
    "SW_ACCESO": [
        {"clave": "aplicacion", "tipo": "string", "obligatorio": True},
        {"clave": "tipo_acceso", "tipo": "enum", "opciones": ["alta", "baja", "reset_clave", "permiso"]},
    ],
}
TRANSICIONES = {
    "nuevo": ["asignado", "cancelado"],
    "asignado": ["en_progreso", "cancelado"],
    "en_progreso": ["en_espera", "resuelto", "cancelado"],
    "en_espera": ["en_progreso", "cancelado"],
    "resuelto": ["cerrado", "en_progreso"],
    "cerrado": [],
    "cancelado": [],
}


def sla_categoria(cod):
    r, s = BASE_SLA[cod]
    return {p: {"respuesta_min": int(r * PRIO_RESP[p]), "resolucion_min": int(s * PRIO_RES[p])}
            for p in PRIO_RESP}


def gen_categorias():
    return [{
        "_id": cod,
        "nombre": NOMBRES[cod],
        "activa": cod != "SW_ACCESO" or True,
        "campos_personalizados": CAMPOS[cod],
        "sla": sla_categoria(cod),
        "transiciones": TRANSICIONES,
        "schema_version": 1,
    } for cod in NOMBRES]


# ---------------------------------------------------------------- agentes
# (nombre, nivel, habilidades(cat.), sede, capacidad, activo)
AGENTES_DEF = [
    ("Diego Paz", 2, ["HW_FALLA", "SW_ACCESO"], "Sede Norte", 8, True),
    ("Lucía Ferreyra", 1, ["HW_FALLA", "SW_ACCESO"], "Sede Centro", 10, True),
    ("Martín Olivera", 2, ["HW_FALLA", "COMPRAS"], "Sede Sur", 8, True),
    ("Carla Benítez", 1, ["SW_ACCESO", "COMPRAS"], "Sede Centro", 10, True),
    ("Javier Rossi", 2, ["RED_CONEX", "HW_FALLA"], "Sede Norte", 4, True),   # red: cuello de botella
    ("Paula Giménez", 2, ["RED_CONEX"], "Sede Centro", 5, True),               # red: cuello de botella
    ("Nicolás Aguirre", 1, ["MANT_EDIL"], "Sede Sur", 8, True),
    ("Romina Castro", 1, ["MANT_EDIL", "COMPRAS"], "Sede Norte", 8, True),
    ("Federico Luna", 3, ["SW_ACCESO", "HW_FALLA", "COMPRAS"], "Sede Centro", 6, True),
    ("Sergio Molina", 1, ["HW_FALLA"], "Sede Sur", 8, False),                  # inactivo (caso límite)
]


def gen_agentes():
    docs = []
    for i, (nom, niv, hab, sede, cap, act) in enumerate(AGENTES_DEF, 1):
        docs.append({
            "_id": oid("66f1a2b3c4d5e6f7a8", i + 0xa000),
            "nombre": nom,
            "email": nom.lower().replace(" ", ".").replace("í", "i").replace("é", "e")
                     .replace("á", "a").replace("ú", "u") + "@org.edu",
            "rol": "tecnico" if niv < 3 else "supervisor",
            "nivel": niv,
            "habilidades": hab,
            "sede_base": sede,
            "turno": {"dias": [1, 2, 3, 4, 5], "desde": "08:00", "hasta": "16:00"}
                     if i % 2 == 0 else {"dias": [1, 2, 3, 4, 5], "desde": "12:00", "hasta": "20:00"},
            "capacidad_maxima": cap,
            "carga_actual": 0,          # se recalcula al final
            "activo": act,
            "schema_version": 1,
        })
    return docs


# ---------------------------------------------------------------- clientes
NOMBRES_P = ["Marta", "Hugo", "Sofía", "Tomás", "Valeria", "Andrés", "Camila", "Ramiro", "Julieta",
             "Esteban", "Lorena", "Gabriel", "Mariana", "Pablo", "Noelia", "Ignacio", "Daniela", "Cristian"]
APELLIDOS = ["Quiroga", "Sosa", "Peralta", "Domínguez", "Acosta", "Villalba", "Herrera", "Maidana",
             "Ledesma", "Correa", "Navarro", "Ibarra", "Cabrera", "Ponce", "Figueroa", "Torres"]
AREAS = ["Departamento de Matemática", "Administración", "Biblioteca", "Laboratorio de Física",
         "Secretaría Académica", "Bedelía", "Rectorado", "Departamento de Sistemas"]
TIPOS_CLIENTE = ["docente", "administrativo", "estudiante"]
EQUIPO_TIPOS = [("notebook", ["Lenovo", "HP", "Dell"]), ("pc", ["HP", "Dell", "Acer"]),
                ("impresora", ["Brother", "Epson", "HP"]), ("monitor", ["LG", "Samsung"])]


def sin_tildes(s):
    for a, b in zip("áéíóúñ", "aeioun"):
        s = s.replace(a, b)
    return s


def gen_clientes():
    docs, inv = [], 4000
    for i in range(1, N_CLIENTES + 1):
        nom = f"{rnd.choice(NOMBRES_P)} {rnd.choice(APELLIDOS)}"
        equipos = []
        for _ in range(rnd.randint(1, 5)):
            inv += 1
            tipo, marcas = rnd.choice(EQUIPO_TIPOS)
            eq = {"inventario": f"INV-{inv:06d}", "tipo": tipo, "marca": rnd.choice(marcas)}
            if rnd.random() < 0.7:
                eq["modelo"] = rnd.choice(["T14", "ProBook", "Latitude", "L3250", "27UL500", "S24"])
            if rnd.random() < 0.6:
                eq["garantia_hasta"] = fecha(datetime(2026, 1, 1, tzinfo=timezone.utc)
                                              + timedelta(days=rnd.randint(-200, 900)))
            equipos.append(eq)
        docs.append({
            "_id": oid("66f1a2b3c4d5e6f7a8", i + 0xb000),
            "nombre": nom,
            "email": f"{sin_tildes(nom).lower().replace(' ', '.')}{i}@org.edu",
            "tipo": rnd.choices(TIPOS_CLIENTE, [5, 4, 2])[0],
            "area": rnd.choice(AREAS),
            "sede": rnd.choice(SEDES),
            "prioritario": rnd.random() < 0.12,
            "equipos": equipos,
            "creado": fecha(datetime(2025, 2, 1, tzinfo=timezone.utc) + timedelta(days=rnd.randint(0, 300))),
            "schema_version": 1,
        })
    return docs


# ---------------------------------------------------------------- tickets
TITULOS = {
    "HW_FALLA": ["La notebook no enciende", "El monitor no da video", "La impresora hace ruido y no imprime",
                 "La PC se reinicia sola", "Teclado con teclas que no responden", "Equipo muy lento al iniciar"],
    "RED_CONEX": ["Sin internet en el laboratorio", "Wifi intermitente en biblioteca", "Cortes de red en secretaría",
                  "Lentitud extrema en la VLAN de administración", "Switch del piso 2 sin enlace"],
    "MANT_EDIL": ["Luz quemada en aula", "Pérdida de agua en el baño", "Puerta que no cierra", "Pintura descascarada",
                  "Silla rota en sala de profesores"],
    "COMPRAS": ["Compra de toner", "Pedido de mouses y teclados", "Reposición de cables HDMI", "Compra de licencias",
                "Compra de disco SSD"],
    "SW_ACCESO": ["Alta de usuario en el sistema académico", "Reset de clave de correo", "Permiso a carpeta compartida",
                  "Baja de usuario egresado", "No puedo ingresar al campus virtual"],
}
TEXTOS_AGENTE = ["Reviso el caso y te cuento.", "Ya estoy trabajando en esto.", "Necesito más datos para avanzar.",
                 "Pasé por el lugar, estoy esperando un repuesto.", "Probé una solución, ¿podés confirmar si funciona?",
                 "Lo escalo al equipo de nivel 2."]
TEXTOS_SOLICITANTE = ["Sigue igual.", "Gracias, quedo atento.", "Es urgente, tengo clase en una hora.",
                      "Ahora funciona, gracias.", "Les adjunto una foto."]
EDIFICIOS = ["Edificio A", "Edificio B", "Biblioteca", "Laboratorios"]
PRIORIDADES = ["critica", "alta", "media", "baja"]
PESO_PRIO = [5, 25, 45, 25]
PESO_CAT = {"HW_FALLA": 30, "RED_CONEX": 22, "MANT_EDIL": 14, "COMPRAS": 12, "SW_ACCESO": 22}
P_INCUMPLE = {"HW_FALLA": 0.06, "RED_CONEX": 0.32, "MANT_EDIL": 0.07, "COMPRAS": 0.06, "SW_ACCESO": 0.05}
P_ABIERTO_RECIENTE = 0.7      # de los tickets de los últimos 21 días, fracción que sigue abierta hoy
PESO_DIA = [3.0, 1.5, 1.2, 1.2, 1.0, 0.15, 0.1]      # lunes=0 ... domingo=6 (picos de lunes)
PESO_HORA = {8: 3, 9: 5, 10: 6, 11: 5, 12: 3, 13: 3, 14: 4, 15: 4, 16: 3, 17: 2}


def fecha_creacion():
    dias = (AHORA - INICIO).days - 1
    while True:
        d = INICIO + timedelta(days=rnd.randint(0, dias))
        if rnd.random() < PESO_DIA[d.weekday()] / 3.0:
            h = rnd.choices(list(PESO_HORA), list(PESO_HORA.values()))[0]
            return d.replace(hour=h, minute=rnd.randint(0, 59), second=0)


def campos_personalizados(cod, cliente):
    if cod == "HW_FALLA":
        eq = rnd.choice([e for e in cliente["equipos"]])
        c = {"equipo": {"inventario": eq["inventario"], "tipo": eq["tipo"], "marca": eq["marca"]},
             "sintoma": rnd.choice(["no_enciende", "lento", "ruido", "sin_video"])}
        if rnd.random() < 0.85:                    # opcional
            c["garantia_vigente"] = rnd.random() < 0.4
        return c
    if cod == "RED_CONEX":
        return {"sede": cliente["sede"], "vlan": rnd.choice([10, 20, 30, 40, 100, 200]),
                "equipos_afectados": rnd.choice([1, 1, 2, 5, 12, 30]),
                "tipo_falla": rnd.choice(["sin_enlace", "intermitente", "lento", "wifi"])}
    if cod == "MANT_EDIL":
        return {"ubicacion": {"edificio": rnd.choice(EDIFICIOS), "piso": rnd.randint(0, 4),
                              "aula": f"{rnd.randint(1, 30)}"},
                "tipo_tarea": rnd.choice(["electricidad", "plomeria", "pintura", "mobiliario"])}
    if cod == "COMPRAS":
        c = {"centro_costo": f"CC-{rnd.randint(100, 140)}", "importe": round(rnd.uniform(15000, 900000), 2)}
        if rnd.random() < 0.5:
            c["proveedor"] = rnd.choice(["TecnoSur", "Insumos SA", "CompuMax"])
        return c
    return {"aplicacion": rnd.choice(["Sistema académico", "Correo", "Campus virtual", "Carpeta compartida"]),
            "tipo_acceso": rnd.choice(["alta", "baja", "reset_clave", "permiso"])}


def gen_tickets(categorias, agentes, clientes):
    cat_sla = {c["_id"]: c["sla"] for c in categorias}
    creaciones = sorted(fecha_creacion() for _ in range(N_TICKETS))
    borradores = []

    # --- 1) línea de tiempo teórica de cada ticket
    for dt in creaciones:
        cod = rnd.choices(list(PESO_CAT), list(PESO_CAT.values()))[0]
        prio = rnd.choices(PRIORIDADES, PESO_PRIO)[0]
        cli = rnd.choice(clientes)
        if cli["prioritario"] and prio in ("baja", "media"):
            prio = "alta"
        lim = cat_sla[cod][prio]
        p = P_INCUMPLE[cod]

        def ratio():
            return rnd.uniform(1.05, 2.4) if rnd.random() < p else rnd.uniform(0.15, 0.95)

        t_resp = max(5, int(lim["respuesta_min"] * ratio()))
        t_res = max(t_resp + 15, int(lim["resolucion_min"] * ratio()))
        b = {"dt": dt, "cod": cod, "prio": prio, "cli": cli, "lim": lim, "t_resp": t_resp, "t_res": t_res,
             "cancela": None, "reabre": False, "agente": None}
        if rnd.random() < 0.04:
            b["cancela"] = rnd.randint(20, 3000)          # minutos desde la creación
        elif rnd.random() < 0.05:
            b["reabre"] = True
        borradores.append(b)

    # --- 2) estado "hoy" de cada ticket (qué eventos ya ocurrieron)
    for b in borradores:
        dt = b["dt"]
        edad_min = int((AHORA - dt).total_seconds() // 60)
        if edad_min < 21 * 24 * 60 and b["cancela"] is None and rnd.random() < P_ABIERTO_RECIENTE:
            b["t_res"] = edad_min + rnd.randint(60, 4000)      # todavía sin resolver hoy
            b["reabre"] = False
        t_asig = min(rnd.randint(3, 40), max(3, b["t_resp"] - 2))
        b["t_asig"] = t_asig
        if b["cancela"] is not None and dt + minutos(b["cancela"]) <= AHORA:
            b["final"] = "cancelado"
            b["necesita_agente"] = b["cancela"] > t_asig and rnd.random() < 0.6
            b["t_cancel"] = b["cancela"]
        elif dt + minutos(b["t_res"]) <= AHORA:
            t_cierre = b["t_res"] + rnd.randint(4 * 60, 48 * 60)
            b["final"] = "cerrado" if dt + minutos(t_cierre) <= AHORA else "resuelto"
            b["t_cierre"] = t_cierre
            b["necesita_agente"] = True
        elif dt + minutos(t_asig) <= AHORA:
            b["final"] = rnd.choices(["asignado", "en_progreso", "en_espera"], [2, 6, 2])[0]
            b["necesita_agente"] = True
        else:
            b["final"] = "nuevo"
            b["necesita_agente"] = False

    # --- 3) asignación de agentes (respeta la capacidad en los tickets abiertos)
    carga = {a["_id"]["$oid"]: 0 for a in agentes}
    abiertos = ("asignado", "en_progreso", "en_espera")
    for b in sorted(borradores, key=lambda x: x["dt"]):
        if not b["necesita_agente"]:
            continue
        candidatos = [a for a in agentes if a["activo"] and b["cod"] in a["habilidades"]]
        if b["final"] in abiertos:
            candidatos = [a for a in candidatos if carga[a["_id"]["$oid"]] < a["capacidad_maxima"]]
            if not candidatos:                 # nadie con cupo: queda sin asignar (caso límite)
                b["final"], b["necesita_agente"] = "nuevo", False
                continue
            elegido = min(candidatos, key=lambda a: carga[a["_id"]["$oid"]] / a["capacidad_maxima"])
            carga[elegido["_id"]["$oid"]] += 1
        else:
            elegido = rnd.choice(candidatos)   # historial: sin restricción de cupo
        b["agente"] = elegido
    for a in agentes:
        a["carga_actual"] = carga[a["_id"]["$oid"]]

    # --- 4) documentos finales
    tickets = []
    for n, b in enumerate(borradores, 1):
        dt, cod, ag, cli = b["dt"], b["cod"], b["agente"], b["cli"]
        estado = b["final"]
        lim = b["lim"]
        hist = [{"fecha": fecha(dt), "tipo": "estado", "de": None, "a": "nuevo"}]
        comentarios, prim_resp, resuelto_en = [], None, None

        def ultimo_evento():
            return datetime.strptime(hist[-1]["fecha"]["$date"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

        def evento(cuando, de, a):
            hist.append({"fecha": fecha(cuando), "tipo": "estado", "de": de, "a": a})

        if ag is not None:
            t_asig = dt + minutos(b["t_asig"])
            evento(t_asig, "nuevo", "asignado")
            hist[-1]["agente"] = ag["nombre"]
            ult = "asignado"
            if estado != "asignado" and estado != "cancelado" or (estado == "cancelado" and b["t_cancel"] > b["t_asig"] + 15):
                t_prog = t_asig + minutos(rnd.randint(3, 25))
                if t_prog <= AHORA:
                    evento(t_prog, "asignado", "en_progreso")
                    ult = "en_progreso"
            if estado == "en_espera" and ult == "en_progreso":
                evento(min(AHORA, ultimo_evento() + minutos(rnd.randint(30, 120))), "en_progreso", "en_espera")
                ult = "en_espera"
            # primera respuesta del agente
            if estado in ("en_progreso", "en_espera", "resuelto", "cerrado") or (estado == "cancelado" and ult == "en_progreso"):
                prim_resp = max(dt + minutos(b["t_resp"]), t_asig + minutos(2))
                if prim_resp > AHORA:
                    prim_resp = None
                else:
                    comentarios.append({"autor": {"tipo": "agente", "nombre": ag["nombre"]},
                                        "texto": rnd.choice(TEXTOS_AGENTE), "fecha": fecha(prim_resp)})
            if estado in ("resuelto", "cerrado"):
                resuelto_en = min(AHORA, max(dt + minutos(b["t_res"]), ultimo_evento() + minutos(10)))
                if prim_resp is None:
                    prim_resp = dt + minutos(b["t_resp"])
                    comentarios.append({"autor": {"tipo": "agente", "nombre": ag["nombre"]},
                                        "texto": rnd.choice(TEXTOS_AGENTE), "fecha": fecha(prim_resp)})
                resuelto_en = max(resuelto_en, prim_resp + minutos(5))
                # comentarios adicionales entre la primera respuesta y la resolución
                for _ in range(rnd.choice([0, 0, 1, 2, 3, 4])):
                    span = max(2, int((resuelto_en - prim_resp).total_seconds() // 60))
                    cuando = prim_resp + minutos(rnd.randint(1, span))
                    por_agente = rnd.random() < 0.55
                    comentarios.append({
                        "autor": {"tipo": "agente", "nombre": ag["nombre"]} if por_agente
                                 else {"tipo": "solicitante", "nombre": cli["nombre"]},
                        "texto": rnd.choice(TEXTOS_AGENTE if por_agente else TEXTOS_SOLICITANTE),
                        "fecha": fecha(cuando)})
                evento(resuelto_en, "en_progreso", "resuelto")
                if b["reabre"]:
                    t_reap = resuelto_en + minutos(rnd.randint(30, 600))
                    if t_reap < AHORA - timedelta(days=1):
                        evento(t_reap, "resuelto", "en_progreso")
                        resuelto_en2 = t_reap + minutos(rnd.randint(60, 900))
                        evento(resuelto_en2, "en_progreso", "resuelto")
                        resuelto_en = resuelto_en2
                    else:
                        b["reabre"] = False
                if estado == "cerrado":
                    evento(min(AHORA, max(dt + minutos(b["t_cierre"]), resuelto_en + minutos(240))), "resuelto", "cerrado")
        if estado == "cancelado":
            evento(min(AHORA, max(dt + minutos(b["t_cancel"]), ultimo_evento() + minutos(1))), hist[-1]["a"], "cancelado")

        comentarios.sort(key=lambda c: c["fecha"]["$date"])
        # ---- SLA
        resp_limite = dt + minutos(lim["respuesta_min"])
        res_limite = dt + minutos(lim["resolucion_min"])
        sla = {"respuesta_limite": fecha(resp_limite), "resolucion_limite": fecha(res_limite)}
        if prim_resp:
            sla["primera_respuesta_en"] = fecha(prim_resp)
        if estado == "cancelado":
            incumplido = False
        else:
            r_ok = (prim_resp or AHORA) <= resp_limite
            s_ok = (resuelto_en or AHORA) <= res_limite
            incumplido = not (r_ok and s_ok)
        sla["incumplido"] = incumplido

        ultimo_mov = max(datetime.strptime(h["fecha"]["$date"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                         for h in hist + comentarios)
        t = {
            "_id": oid("66f1a2b3c4d5e6f7a8", n + 0xc000),
            "numero": f"INC-2026-{n:06d}",
            "titulo": rnd.choice(TITULOS[cod]),
            "descripcion": "Detalle del problema reportado por el solicitante." if rnd.random() > 0.03
                           else "Detalle extenso. " + "El problema se repite desde hace varios días. " * 25,
            "categoria": {"codigo": cod, "nombre": NOMBRES[cod]},
            "prioridad": b["prio"],
            "estado": estado,
            "solicitante": {"cliente_id": cli["_id"], "nombre": cli["nombre"], "email": cli["email"], "sede": cli["sede"]},
        }
        if ag is not None:
            t["agente"] = {"agente_id": ag["_id"], "nombre": ag["nombre"]}
        t["campos_personalizados"] = campos_personalizados(cod, cli)
        if rnd.random() < 0.35:
            t["etiquetas"] = rnd.sample(["urgente", "recurrente", "garantia", "sede_norte", "clase_en_curso", "evento"],
                                         rnd.randint(1, 3))
        if cod == "MANT_EDIL" and rnd.random() < 0.6:
            t["adjuntos"] = [{"nombre": f"foto_{n}.jpg", "tipo": "image/jpeg", "tamano_kb": rnd.randint(150, 2800)}]
        t["sla"] = sla
        t["comentarios"] = comentarios
        t["historial"] = hist
        t["metricas"] = {"cant_comentarios": len(comentarios), "reaperturas": 1 if b["reabre"] else 0}
        if resuelto_en:
            t["resuelto_en"] = fecha(resuelto_en)
        if estado == "cerrado" and rnd.random() < 0.7:
            media = 2.6 if cod == "RED_CONEX" else 4.2
            t["satisfaccion"] = {"puntaje": max(1, min(5, round(rnd.gauss(media, 0.9)))),
                                 **({"comentario": "Resuelto, gracias."} if rnd.random() < 0.3 else {})}
        t["creado"] = fecha(dt)
        t["actualizado"] = fecha(ultimo_mov)
        t["schema_version"] = 1
        tickets.append(t)
    return tickets


# ---------------------------------------------------------------- main
def escribir(nombre, docs):
    with open(OUT / f"{nombre}.json", "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"  {nombre:<11} {len(docs):>4} documentos")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    categorias, agentes, clientes = gen_categorias(), gen_agentes(), gen_clientes()
    tickets = gen_tickets(categorias, agentes, clientes)
    contadores = [{"_id": "ticket-2026", "valor": len(tickets)}]
    print("Escribiendo en", OUT)
    for nombre, docs in [("categorias", categorias), ("agentes", agentes), ("clientes", clientes),
                         ("tickets", tickets), ("contadores", contadores)]:
        escribir(nombre, docs)


if __name__ == "__main__":
    main()

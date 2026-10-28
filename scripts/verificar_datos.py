#!/usr/bin/env python3
"""
Verifica los archivos generados en data/ SIN necesitar MongoDB.
Chequea integridad referencial, coherencia de contadores y transiciones,
y muestra los patrones que se sembraron a propósito.

Uso:  python scripts/verificar_datos.py
"""
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
ABIERTOS = {"asignado", "en_progreso", "en_espera"}


def cargar(nombre):
    with open(DATA / f"{nombre}.json", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def f(d):
    return datetime.strptime(d["$date"], "%Y-%m-%dT%H:%M:%SZ")


categorias = {c["_id"]: c for c in cargar("categorias")}
agentes = {a["_id"]["$oid"]: a for a in cargar("agentes")}
clientes = {c["_id"]["$oid"]: c for c in cargar("clientes")}
tickets = cargar("tickets")
contador = cargar("contadores")[0]

errores = []


def check(cond, msg):
    if not cond:
        errores.append(msg)


# --- integridad básica
numeros = [t["numero"] for t in tickets]
check(len(set(numeros)) == len(numeros), "números de ticket repetidos")
check(contador["valor"] == len(tickets), "contador != cantidad de tickets")
check(numeros[-1] == f"INC-2026-{contador['valor']:06d}", "último número no coincide con el contador")

carga = Counter()
for t in tickets:
    n = t["numero"]
    check(t["categoria"]["codigo"] in categorias, f"{n}: categoría inexistente")
    check(t["solicitante"]["cliente_id"]["$oid"] in clientes, f"{n}: cliente inexistente")
    if "agente" in t:
        check(t["agente"]["agente_id"]["$oid"] in agentes, f"{n}: agente inexistente")
        if t["estado"] in ABIERTOS:
            carga[t["agente"]["agente_id"]["$oid"]] += 1
    else:
        check(t["estado"] in ("nuevo", "cancelado"), f"{n}: sin agente pero en estado {t['estado']}")
    check(t["metricas"]["cant_comentarios"] == len(t["comentarios"]), f"{n}: cant_comentarios incorrecto")
    check(t["historial"][-1]["a"] == t["estado"], f"{n}: último historial != estado")
    # transiciones válidas según la categoría
    trans = categorias[t["categoria"]["codigo"]]["transiciones"]
    for h in t["historial"][1:]:
        check(h["a"] in trans.get(h["de"], []), f"{n}: transición inválida {h['de']} -> {h['a']}")
    # fechas en orden
    fechas = [f(h["fecha"]) for h in t["historial"]]
    check(fechas == sorted(fechas), f"{n}: historial desordenado")
    check(f(t["creado"]) <= f(t["actualizado"]), f"{n}: creado > actualizado")

for aid, a in agentes.items():
    check(a["carga_actual"] == carga[aid], f"{a['nombre']}: carga_actual {a['carga_actual']} != abiertos {carga[aid]}")
    check(a["carga_actual"] <= a["capacidad_maxima"], f"{a['nombre']}: supera su capacidad")

# --- resumen
print(f"Tickets: {len(tickets)} | Clientes: {len(clientes)} | Agentes: {len(agentes)} | Categorías: {len(categorias)}")
print("\nEstados:", dict(Counter(t["estado"] for t in tickets)))
print("Sin agente:", sum("agente" not in t for t in tickets),
      "| Reabiertos:", sum(t["metricas"]["reaperturas"] > 0 for t in tickets),
      "| Sin comentarios:", sum(not t["comentarios"] for t in tickets),
      "| Con adjuntos:", sum("adjuntos" in t for t in tickets))

dias = Counter(f(t["creado"]).weekday() for t in tickets)
nombres = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
print("\nTickets por día de la semana:", {nombres[d]: dias[d] for d in range(7)})

por_cat = defaultdict(lambda: [0, 0])
for t in tickets:
    if t["estado"] != "cancelado":
        por_cat[t["categoria"]["codigo"]][0] += 1
        por_cat[t["categoria"]["codigo"]][1] += t["sla"]["incumplido"]
print("\nSLA incumplido por categoría:")
for c, (n, i) in sorted(por_cat.items(), key=lambda x: -x[1][1] / x[1][0]):
    print(f"  {c:<10} {i:>3}/{n:<3} = {100 * i / n:5.1f}%")

print("\nCarga actual vs capacidad:")
for aid, a in agentes.items():
    print(f"  {a['nombre']:<16} {a['carga_actual']:>2}/{a['capacidad_maxima']:<2} {'(TOPE)' if a['carga_actual'] == a['capacidad_maxima'] else ''}"
          f"{'(inactivo)' if not a['activo'] else ''}")

print("\n" + ("OK: sin errores de integridad." if not errores else f"{len(errores)} ERRORES:"))
for e in errores[:25]:
    print("  -", e)
raise SystemExit(1 if errores else 0)

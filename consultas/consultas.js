// Consultas de Sentinel (mongosh).
// Ejecutar todas:  mongosh sentinel --file consultas/consultas.js
// o copiar y pegar una por una en mongosh.
//
// Los resultados "esperados" corresponden a los archivos de data/ tal como se entregan.
// Nota: los datos de prueba están "congelados" al 2026-10-27 18:00 UTC, por eso las consultas
// que hablan de "ahora" usan AHORA y no new Date().
db = db.getSiblingDB("sentinel");
const AHORA = ISODate("2026-10-27T18:00:00Z");
const ABIERTOS = ["asignado", "en_progreso", "en_espera"];

function titulo(t) { print("\n==== " + t + " ===="); }

// ---------------------------------------------------------------------------
titulo("Q1 · Comparación: tickets abiertos con el SLA de resolución ya vencido");
// Objetivo: que el supervisor vea qué casos están fuera de plazo hoy.
// Operadores: $in (pertenencia) y $lt (comparación de fechas).
// Esperado: 24 tickets (con los datos de prueba actuales).
printjson(db.tickets.find(
  { estado: { $in: ABIERTOS }, "sla.resolucion_limite": { $lt: AHORA } },
  { numero: 1, "categoria.codigo": 1, estado: 1, "sla.resolucion_limite": 1, _id: 0 }
).toArray());

// ---------------------------------------------------------------------------
titulo("Q2 · Comparación: tickets reabiertos o con muchos comentarios");
// Objetivo: detectar casos problemáticos (el cliente no quedó conforme o el caso se complicó).
// Operadores: $gt, $gte dentro de un $or.
// Esperado: 80 tickets en total; el .limit(10) muestra 10.
printjson(db.tickets.find(
  { $or: [{ "metricas.reaperturas": { $gt: 0 } }, { "metricas.cant_comentarios": { $gte: 4 } }] },
  { numero: 1, estado: 1, metricas: 1, _id: 0 }
).limit(10).toArray());

// ---------------------------------------------------------------------------
titulo("Q3 · Operadores lógicos: urgentes y en riesgo");
// Objetivo: lista de intervención inmediata = (crítica o alta) y abierto y (SLA ya incumplido o sin agente).
// Operadores: $and implícito, $in, $or.
// Esperado: 12 tickets.
printjson(db.tickets.find({
  prioridad: { $in: ["critica", "alta"] },
  estado: { $in: ["nuevo"].concat(ABIERTOS) },
  $or: [{ "sla.incumplido": true }, { agente: { $exists: false } }]
}, { numero: 1, prioridad: 1, estado: 1, "sla.incumplido": 1, _id: 0 }).toArray());

// ---------------------------------------------------------------------------
titulo("Q4 · Atributos anidados: notebooks con falla de hardware en Sede Norte");
// Objetivo: ver el parque de equipos que más falla en una sede. Usa dot notation en 3 niveles.
// Esperado: 5.
printjson(db.tickets.countDocuments({
  "categoria.codigo": "HW_FALLA",
  "solicitante.sede": "Sede Norte",
  "campos_personalizados.equipo.tipo": "notebook"
}));

// ---------------------------------------------------------------------------
titulo("Q5 · Arreglos: tickets etiquetados a la vez como 'urgente' y 'recurrente'");
// Objetivo: encontrar problemas repetitivos que además son críticos para el solicitante.
// Operador de arreglo: $all.
// Esperado: 13 tickets.
printjson(db.tickets.find(
  { etiquetas: { $all: ["urgente", "recurrente"] } },
  { numero: 1, etiquetas: 1, estado: 1, _id: 0 }
).toArray());

// ---------------------------------------------------------------------------
titulo("Q6 · Proyección, orden y límite: próximos 10 vencimientos de SLA");
// Objetivo: la "bandeja" priorizada: lo que vence primero entre los casos abiertos.
// Esperado: 10 documentos con solo 5 campos, ordenados por vencimiento ascendente.
printjson(db.tickets.find(
  { estado: { $in: ABIERTOS } },
  { numero: 1, titulo: 1, estado: 1, "agente.nombre": 1, "sla.resolucion_limite": 1, _id: 0 }
).sort({ "sla.resolucion_limite": 1 }).limit(10).toArray());

// ---------------------------------------------------------------------------
titulo("Q7 · Aggregate: cumplimiento de SLA por categoría");
// Objetivo: indicador #1 del análisis. ¿Qué categoría incumple más? (excluye cancelados)
// Esperado: RED_CONEX 44.9% (31/69), HW_FALLA 25.3% (20/79), MANT_EDIL 21.2% (7/33), SW_ACCESO 20.4% (11/54), COMPRAS 15.2% (5/33).
printjson(db.tickets.aggregate([
  { $match: { estado: { $ne: "cancelado" } } },
  { $group: {
      _id: "$categoria.codigo",
      total: { $sum: 1 },
      incumplidos: { $sum: { $cond: ["$sla.incumplido", 1, 0] } } } },
  { $project: {
      total: 1, incumplidos: 1,
      pct_incumplimiento: { $round: [{ $multiply: [{ $divide: ["$incumplidos", "$total"] }, 100] }, 1] } } },
  { $sort: { pct_incumplimiento: -1 } }
]).toArray());

// ---------------------------------------------------------------------------
titulo("Q8 · Aggregate: tiempo de resolución por categoría (horas)");
// Objetivo: indicador #2 (TMR). Solo tickets que tienen resuelto_en. $dateDiff requiere MongoDB 5.0+.
// Esperado: TMR aprox.: MANT_EDIL 36.0 h, COMPRAS 34.2 h, HW_FALLA 14.0 h, SW_ACCESO 8.9 h, RED_CONEX 8.5 h.
printjson(db.tickets.aggregate([
  { $match: { resuelto_en: { $exists: true } } },
  { $project: {
      cat: "$categoria.codigo",
      horas: { $divide: [{ $dateDiff: { startDate: "$creado", endDate: "$resuelto_en", unit: "minute" } }, 60] } } },
  { $group: { _id: "$cat", tickets: { $sum: 1 }, tmr_horas: { $avg: "$horas" },
              min_horas: { $min: "$horas" }, max_horas: { $max: "$horas" }, desvio: { $stdDevPop: "$horas" } } },
  { $project: { tickets: 1, min_horas: { $round: ["$min_horas", 1] }, max_horas: { $round: ["$max_horas", 1] },
                tmr_horas: { $round: ["$tmr_horas", 1] }, desvio: { $round: ["$desvio", 1] } } },
  { $sort: { tmr_horas: -1 } }
]).toArray());

// ---------------------------------------------------------------------------
titulo("Q9 · Agrupamiento con estadística: tickets creados por día de la semana");
// Objetivo: confirmar el patrón de los lunes. $isoDayOfWeek: 1=lunes ... 7=domingo.
// Esperado: lunes 101 tickets (36.1%), martes 53, miércoles 42, jueves 42, viernes 34, sábado 6, domingo 2.
printjson(db.tickets.aggregate([
  { $group: { _id: { $isoDayOfWeek: "$creado" }, tickets: { $sum: 1 } } },
  { $setWindowFields: { output: { total: { $sum: "$tickets", window: { documents: ["unbounded", "unbounded"] } } } } },
  { $project: { tickets: 1, pct_del_total: { $round: [{ $multiply: [{ $divide: ["$tickets", "$total"] }, 100] }, 1] } } },
  { $sort: { _id: 1 } }
]).toArray());

// ---------------------------------------------------------------------------
titulo("Q10 · Aggregate: carga de trabajo vs. capacidad de cada agente");
// Objetivo: indicador #3. Detecta agentes al límite (distribución del trabajo).
// Esperado: 9 agentes activos: 50% (Diego Paz, Martín Olivera, Javier Rossi, Federico Luna), 40% (Lucía, Carla, Paula), 25% (Nicolás), 12% (Romina).
printjson(db.agentes.aggregate([
  { $match: { activo: true } },
  { $project: { _id: 0, nombre: 1, carga_actual: 1, capacidad_maxima: 1,
                ocupacion_pct: { $round: [{ $multiply: [{ $divide: ["$carga_actual", "$capacidad_maxima"] }, 100] }, 0] } } },
  { $sort: { ocupacion_pct: -1 } }
]).toArray());

// ---------------------------------------------------------------------------
titulo("Q11 · Compleja ($lookup + $unwind): satisfacción por agente y por habilidad");
// Objetivo: cruzar tickets cerrados con la encuesta y los datos del agente (colección distinta).
// Muestra el costo de referenciar: acá sí hace falta un $lookup porque pedimos 'sede_base' y 'nivel'.
// Esperado: Los más bajos: Paula Giménez 2.39 (31 encuestas) y Javier Rossi 2.93 (14); el resto entre 3.89 y 4.44.
printjson(db.tickets.aggregate([
  { $match: { estado: "cerrado", "satisfaccion.puntaje": { $exists: true } } },
  { $group: { _id: "$agente.agente_id", encuestas: { $sum: 1 }, puntaje_prom: { $avg: "$satisfaccion.puntaje" } } },
  { $lookup: { from: "agentes", localField: "_id", foreignField: "_id", as: "agente" } },
  { $unwind: "$agente" },
  { $project: { _id: 0, agente: "$agente.nombre", nivel: "$agente.nivel", sede: "$agente.sede_base",
                encuestas: 1, puntaje_prom: { $round: ["$puntaje_prom", 2] } } },
  { $sort: { puntaje_prom: 1 } }
]).toArray());

// ---------------------------------------------------------------------------
titulo("Q12 · Búsqueda dinámica (usa el índice wildcard): fallas de red en la VLAN 100");
// Objetivo: buscar por un campo que solo existe en una categoría, sin conocer su ruta en el esquema.
// Esperado: 11 tickets con vlan 100 (se muestran 5).
printjson(db.tickets.find(
  { "campos_personalizados.vlan": 100 },
  { numero: 1, "campos_personalizados.tipo_falla": 1, "campos_personalizados.equipos_afectados": 1, estado: 1, _id: 0 }
).limit(5).toArray());

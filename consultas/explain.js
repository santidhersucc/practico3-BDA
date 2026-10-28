// Análisis de rendimiento con explain("executionStats").
// Ejecutar (después de indices.js):  mongosh sentinel --file consultas/explain.js
//
// Cómo leerlo:
//   etapas          -> IXSCAN = usa índice; COLLSCAN = recorre toda la colección; SORT = ordena en memoria.
//   keysExamined    -> entradas de índice recorridas.
//   docsExamined    -> documentos leídos de la colección (ideal: parecido a nReturned).
//   nReturned       -> documentos devueltos.
db = db.getSiblingDB("sentinel");

function etapas(p) {
  let r = [p.stage];
  if (p.inputStage) r = r.concat(etapas(p.inputStage));
  if (p.inputStages) p.inputStages.forEach(i => { r = r.concat(etapas(i)); });
  return r;
}

function resumen(rotulo, cursor) {
  const e = cursor.explain("executionStats");
  const plan = e.queryPlanner.winningPlan.queryPlan || e.queryPlanner.winningPlan;   // MongoDB 7 puede envolver el plan
  const s = e.executionStats;
  print("  " + rotulo);
  print("     etapas=" + etapas(plan).join(" > ") + " | keysExamined=" + s.totalKeysExamined +
        " | docsExamined=" + s.totalDocsExamined + " | nReturned=" + s.nReturned +
        " | ms=" + s.executionTimeMillis);
}

const ABIERTOS = ["asignado", "en_progreso", "en_espera"];
const diego = db.agentes.findOne({ nombre: "Diego Paz" })._id;

print("\n=== 1) Bandeja del agente (índice compuesto idx_bandeja_agente) ===");
const bandeja = () => db.tickets.find(
  { "agente.agente_id": diego, estado: "en_progreso" }).sort({ "sla.resolucion_limite": 1 });
resumen("SIN índice (fuerza COLLSCAN):", bandeja().hint({ $natural: 1 }));
resumen("CON índice:", bandeja().hint("idx_bandeja_agente"));

print("\n=== 2) Búsqueda por número (índice único uq_ticket_numero) ===");
const porNumero = () => db.tickets.find({ numero: "INC-2026-000142" });
resumen("SIN índice:", porNumero().hint({ $natural: 1 }));
resumen("CON índice:", porNumero().hint("uq_ticket_numero"));

print("\n=== 3) Campo dinámico (índice wildcard idx_wildcard_campos) ===");
const porVlan = () => db.tickets.find({ "campos_personalizados.vlan": 100 });
resumen("SIN índice:", porVlan().hint({ $natural: 1 }));
resumen("CON índice:", porVlan().hint("idx_wildcard_campos"));

print("\n=== 4) Reporte por categoría y período (idx_categoria_creado) ===");
const reporte = () => db.tickets.find(
  { "categoria.codigo": "RED_CONEX", creado: { $gte: ISODate("2026-09-01T00:00:00Z") } });
resumen("SIN índice:", reporte().hint({ $natural: 1 }));
resumen("CON índice:", reporte().hint("idx_categoria_creado"));

print("\nNota: con ~280 documentos la diferencia de milisegundos es mínima; lo relevante es la cantidad de");
print("documentos examinados (docsExamined) y la etapa del plan. Cada índice cuesta espacio y se actualiza");
print("en cada escritura; por eso solo se crean los que respaldan los patrones de acceso reales.");

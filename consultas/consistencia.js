// Pruebas de consistencia: asignación de tickets (RF-06 / CU-02).
// Requiere un replica set (las transacciones no funcionan en una instancia standalone). Ejecutar:
//   mongosh sentinel --file consultas/consistencia.js
//
// La operación toca DOS documentos: el ticket (agente + estado) y el agente (carga_actual).
// Si solo una mitad se completa, la base queda inconsistente. Se prueban cuatro escenarios.
db = db.getSiblingDB("sentinel");
let fallos = 0;
function verificar(desc, cond) { print("   " + (cond ? "OK    " : "FALLA ") + desc); if (!cond) fallos++; }

// ---------- helpers
function ticketPrueba(numero) {
  const cli = db.clientes.findOne();
  const ahora = new Date();
  return {
    numero, titulo: "[PRUEBA] ticket de consistencia", descripcion: "Creado por consistencia.js",
    categoria: { codigo: "HW_FALLA", nombre: "Falla de hardware" }, prioridad: "media", estado: "nuevo",
    solicitante: { cliente_id: cli._id, nombre: cli.nombre, email: cli.email, sede: cli.sede },
    sla: { respuesta_limite: new Date(ahora.getTime() + 4 * 3600e3), resolucion_limite: new Date(ahora.getTime() + 24 * 3600e3), incumplido: false },
    comentarios: [], historial: [{ fecha: ahora, tipo: "estado", de: null, a: "nuevo" }],
    metricas: { cant_comentarios: 0, reaperturas: 0 }, creado: ahora, actualizado: ahora, schema_version: 1
  };
}

// Asignación CON transacción. 'simularFalla' corta la operación entre las dos escrituras.
function asignarConTransaccion(numero, nombreAgente, simularFalla) {
  const session = db.getMongo().startSession();
  const sdb = session.getDatabase("sentinel");
  try {
    session.startTransaction({ readConcern: { level: "snapshot" }, writeConcern: { w: "majority" } });
    const ag = sdb.agentes.findOne({ nombre: nombreAgente, activo: true });
    if (!ag) throw new Error("agente inexistente o inactivo");
    const r1 = sdb.tickets.updateOne({ numero: numero, estado: "nuevo" }, {
      $set: { agente: { agente_id: ag._id, nombre: ag.nombre }, estado: "asignado", actualizado: new Date() },
      $push: { historial: { fecha: new Date(), tipo: "estado", de: "nuevo", a: "asignado", agente: ag.nombre } }
    });
    if (r1.modifiedCount !== 1) throw new Error("el ticket no existe o ya no está en estado 'nuevo'");
    if (simularFalla) throw new Error("falla simulada entre las dos escrituras");
    // Control de capacidad: el incremento solo se aplica si hay cupo, evaluado sobre el propio documento.
    const r2 = sdb.agentes.updateOne(
      { _id: ag._id, $expr: { $lt: ["$carga_actual", "$capacidad_maxima"] } },
      { $inc: { carga_actual: 1 } });
    if (r2.modifiedCount !== 1) throw new Error("el agente alcanzó su capacidad máxima");
    session.commitTransaction();
    return { ok: true };
  } catch (e) {
    try { session.abortTransaction(); } catch (_) { /* no había transacción activa */ }
    return { ok: false, motivo: e.message };
  } finally {
    session.endSession();
  }
}

// Misma operación SIN transacción: dos updates sueltos (para mostrar el problema).
function asignarSinTransaccion(numero, nombreAgente, simularFalla) {
  const ag = db.agentes.findOne({ nombre: nombreAgente });
  db.tickets.updateOne({ numero: numero }, { $set: { agente: { agente_id: ag._id, nombre: ag.nombre }, estado: "asignado" } });
  if (simularFalla) return { ok: false, motivo: "falla simulada entre las dos escrituras" };
  db.agentes.updateOne({ _id: ag._id }, { $inc: { carga_actual: 1 } });
  return { ok: true };
}

// El validador exige el patrón INC-AAAA-NNNNNN; los tickets de prueba usan ese formato con un año ficticio (9999).
db.tickets.deleteMany({ numero: /^INC-9999-/ });          // por si quedó basura de una corrida anterior
const N = [1, 2, 3, 4].map(i => "INC-9999-00000" + i);
db.tickets.insertMany(N.map(ticketPrueba));

const lucia = () => db.agentes.findOne({ nombre: "Lucía Ferreyra" });
const javier = () => db.agentes.findOne({ nombre: "Javier Rossi" });
const estado = n => db.tickets.findOne({ numero: n });

// ---------- Escenario A: éxito
print("\nA) Asignación correcta con transacción");
let c0 = lucia().carga_actual;
let r = asignarConTransaccion(N[0], "Lucía Ferreyra", false);
verificar("la operación devuelve ok", r.ok);
verificar("el ticket quedó 'asignado' a Lucía", estado(N[0]).estado === "asignado" && estado(N[0]).agente.nombre === "Lucía Ferreyra");
verificar("la carga de Lucía subió exactamente 1", lucia().carga_actual === c0 + 1);
verificar("el historial registró la transición", estado(N[0]).historial.length === 2);

// ---------- Escenario B: falla a mitad de camino -> rollback
print("\nB) Falla entre las dos escrituras: la transacción debe deshacer todo");
c0 = lucia().carga_actual;
r = asignarConTransaccion(N[1], "Lucía Ferreyra", true);
verificar("la operación devuelve error (" + r.motivo + ")", !r.ok);
verificar("el ticket sigue en 'nuevo' y sin agente (rollback)", estado(N[1]).estado === "nuevo" && !estado(N[1]).agente);
verificar("la carga de Lucía no cambió", lucia().carga_actual === c0);

// ---------- Escenario C: agente sin cupo
print("\nC) Agente al tope de su capacidad: la asignación debe rechazarse sin dejar rastros");
const j0 = javier();
db.agentes.updateOne({ _id: j0._id }, { $set: { carga_actual: j0.capacidad_maxima } });   // lo llenamos
r = asignarConTransaccion(N[2], "Javier Rossi", false);
verificar("la operación se rechaza (" + r.motivo + ")", !r.ok && /capacidad/.test(r.motivo));
verificar("el ticket sigue en 'nuevo' y sin agente", estado(N[2]).estado === "nuevo" && !estado(N[2]).agente);
verificar("la carga de Javier no superó su capacidad", javier().carga_actual === j0.capacidad_maxima);
db.agentes.updateOne({ _id: j0._id }, { $set: { carga_actual: j0.carga_actual } });         // restauramos

// ---------- Escenario D: el problema sin transacción
print("\nD) La misma falla SIN transacción deja la base inconsistente (demostración del problema)");
c0 = lucia().carga_actual;
r = asignarSinTransaccion(N[3], "Lucía Ferreyra", true);
verificar("ticket 'asignado' a Lucía pero su carga NO subió -> inconsistencia visible",
          estado(N[3]).estado === "asignado" && lucia().carga_actual === c0);

// ---------- limpieza: dejar los datos como estaban
db.tickets.deleteMany({ numero: /^INC-9999-/ });
db.agentes.updateOne({ nombre: "Lucía Ferreyra" }, { $inc: { carga_actual: -1 } });          // deshace la asignación del escenario A
print("\n" + (fallos === 0 ? "Todas las verificaciones pasaron." : fallos + " verificación(es) fallaron."));
print("Datos de prueba eliminados y carga de Lucía restaurada.");

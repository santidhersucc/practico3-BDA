// Índices de Sentinel.  Ejecutar:  mongosh sentinel --file consultas/indices.js
// Cada índice responde a un patrón de acceso de la entrega 1 (sección 9).
db = db.getSiblingDB("sentinel");

// 1) Bandeja del agente: igualdad (agente), igualdad (estado), orden (vencimiento SLA). Regla ESR.
db.tickets.createIndex(
  { "agente.agente_id": 1, estado: 1, "sla.resolucion_limite": 1 },
  { name: "idx_bandeja_agente" });

// 2) Número de ticket: lookup puntual (RF-02) y garantía de unicidad.
db.tickets.createIndex({ numero: 1 }, { unique: true, name: "uq_ticket_numero" });

// 3) Wildcard: campos_personalizados cambia de forma según la categoría (VLAN, inventario, importe...).
db.tickets.createIndex({ "campos_personalizados.$**": 1 }, { name: "idx_wildcard_campos" });

// 4) Reportes por categoría y período (SLA, tiempo medio de resolución).
db.tickets.createIndex({ "categoria.codigo": 1, creado: 1 }, { name: "idx_categoria_creado" });

// Unicidad de correos
db.agentes.createIndex({ email: 1 }, { unique: true, name: "uq_agente_email" });
db.clientes.createIndex({ email: 1 }, { unique: true, name: "uq_cliente_email" });

print("Índices de tickets:");
db.tickets.getIndexes().forEach(i => print("  " + i.name + "  " + JSON.stringify(i.key)));

// Costo de almacenamiento de cada índice (para el análisis costo/beneficio)
const stats = db.tickets.stats();
print("\nTamaño de la colección tickets: " + stats.size + " bytes");
Object.entries(stats.indexSizes).forEach(([n, s]) => print("  índice " + n + ": " + s + " bytes"));

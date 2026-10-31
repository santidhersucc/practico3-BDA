# Sentinel: base poblada, consultas e índices (Entrega Parcial 2)

**Fecha:** Octubre 2026
**Proyecto:** Trabajo Práctico Integrador MongoDB - Base de Datos Aplicada
**Integrantes:** Enzo Parra, Santiago Dhers, Tomas Vogt, Santino Vazquez de Novoa

> Los apartados marcados **COMPLETAR** requieren pegar la salida real de la ejecución. No están rellenados a propósito.

## 1. Alcance de esta entrega

Según el plan de trabajo (semana 2): colecciones creadas y pobladas, scripts reproducibles, las 10 consultas y agregaciones, índices y primeras pruebas de consistencia. La API, los repositorios, el análisis en Python y Docker Compose corresponden a entregas posteriores.

## 2. Implementación y carga de datos

**Scripts:** `scripts/generar_datos.py` (genera los archivos de `data/` con semilla fija), `scripts/verificar_datos.py` (integridad previa a la carga) y `scripts/cargar_datos.py` (crea las colecciones, carga y verifica).

| Colección | Documentos | Observaciones |
| --- | --- | --- |
| `tickets` | 280 | Entidad principal; jul-oct 2026 |
| `clientes` | 60 | Con 1 a 5 equipos embebidos |
| `agentes` | 10 | Uno inactivo; capacidades entre 4 y 10 |
| `categorias` | 5 | HW_FALLA, RED_CONEX, MANT_EDIL, COMPRAS, SW_ACCESO |
| `contadores` | 1 | `ticket-2026` = 280 |
| **Total** | **356** | Supera el mínimo de 100 documentos |

**Variedad y casos límite:** `campos_personalizados` distinto en cada categoría; campos opcionales ausentes (`garantia_vigente`, `proveedor`, `etiquetas`, `adjuntos`, `agente`, `satisfaccion`); tickets cancelados sin agente; tickets reabiertos; tickets sin comentarios; descripciones muy largas; tickets abiertos con el SLA vencido; agente inactivo.

**Patrones sembrados (para el análisis de la entrega final):** el 36% de los tickets se crea los lunes y `RED_CONEX` incumple el SLA en ~45% de los casos, contra 15-25% del resto.

**Validación de esquema:** `tickets` y `agentes` se crean con `$jsonSchema` (campos obligatorios, enums de `estado` y `prioridad`, formato de `numero`, tipos de fecha, `capacidad_maxima` ≥ 1, `carga_actual` ≥ 0).

**Verificación de la carga:** `cargar_datos.py` comprueba que los conteos coincidan con los archivos, que el contador coincida con el último número de ticket, que cada ticket con agente referencie un agente existente y que `carga_actual` de cada agente sea igual a la cantidad de tickets abiertos que tiene.

**Reinicialización:** volver a ejecutar `python scripts/cargar_datos.py` (borra y recrea las colecciones).

**Evidencia de ejecución:** 
(.venv) PS C:\Users\santi\TP_BDA\practico3-BDA> python scripts/generar_datos.py
Escribiendo en C:\Users\santi\TP_BDA\practico3-BDA\data
  categorias     5 documentos
  agentes       10 documentos
  clientes      60 documentos
  tickets      280 documentos
  contadores     1 documentos
(.venv) PS C:\Users\santi\TP_BDA\practico3-BDA> python scripts/cargar_datos.py
Base 'sentinel' en mongodb://localhost:27017/?directConnection=true
  categorias     5 documentos cargados
  agentes       10 documentos cargados
  clientes      60 documentos cargados
  tickets      280 documentos cargados
  contadores     1 documentos cargados

Verificación:
  OK    conteo de categorias coincide con el archivo
  OK    conteo de agentes coincide con el archivo
  OK    conteo de clientes coincide con el archivo
  OK    conteo de tickets coincide con el archivo
  OK    conteo de contadores coincide con el archivo
  OK    contador de numeración == último número de ticket
  OK    todo ticket con agente referencia un agente existente
  OK    carga_actual de cada agente == tickets abiertos que tiene

Carga correcta.

## 3. Consultas

Archivo: `consultas/consultas.js`. Cada consulta incluye objetivo, comando y resultado esperado. Los resultados esperados se calcularon aparte a partir de los datos de `data/`, así que sirven para comprobar que la consulta devuelve lo correcto.

| Id | Tipo pedido en la consigna | Pregunta del dominio | Esperado |
| --- | --- | --- | --- |
| Q1 | Comparación | ¿Qué tickets abiertos ya vencieron su plazo de resolución? | 24 |
| Q2 | Comparación | ¿Qué tickets se reabrieron o tuvieron muchos comentarios? | 80 |
| Q3 | Operadores lógicos | ¿Qué casos críticos/altos abiertos están incumplidos o sin agente? | 12 |
| Q4 | Atributos anidados | ¿Cuántas notebooks con falla hay en Sede Norte? | 5 |
| Q5 | Arreglos | ¿Qué tickets son a la vez "urgente" y "recurrente"? | 13 |
| Q6 | Proyección, orden y límite | ¿Cuáles son los 10 próximos vencimientos de SLA? | 10 documentos |
| Q7 | Agregación | ¿Qué categoría incumple más el SLA? | RED_CONEX 44.9% |
| Q8 | Agregación | ¿Cuánto tarda cada categoría en resolverse? | MANT_EDIL 36.0 h ... RED_CONEX 8.5 h |
| Q9 | Agrupamiento y estadística | ¿Qué día de la semana se crean más tickets? | lunes 101 (36.1%) |
| Q10 | Agregación | ¿Qué tan cerca de su capacidad está cada agente? | 12% a 50% |
| Q11 | Complejidad elegida ($lookup + $unwind) | ¿Cómo valoran la atención los solicitantes, por agente? | Paula Giménez 2.39 ... Diego Paz 4.44 |
| Q12 | Búsqueda dinámica (índice wildcard) | ¿Qué tickets de red afectan a la VLAN 100? | 11 |

**Evidencia de ejecución:** 
Ejecucion archivo indices.js:
Índices de tickets:
  _id_  {"_id":1}
  idx_bandeja_agente  {"agente.agente_id":1,"estado":1,"sla.resolucion_limite":1}
  uq_ticket_numero  {"numero":1}
  idx_wildcard_campos  {"campos_personalizados.$**":1}
  idx_categoria_creado  {"categoria.codigo":1,"creado":1}

Tamaño de la colección tickets: 445179 bytes
  índice _id_: 20480 bytes
  índice idx_bandeja_agente: 20480 bytes
  índice uq_ticket_numero: 20480 bytes
  índice idx_wildcard_campos: 24576 bytes
  índice idx_categoria_creado: 20480 bytes

  Ejecucion archivo explain.js:
  
=== 1) Bandeja del agente (índice compuesto idx_bandeja_agente) ===
  SIN índice (fuerza COLLSCAN):
     etapas=SORT > COLLSCAN | keysExamined=0 | docsExamined=280 | nReturned=2 | ms=10
  CON índice:
     etapas=FETCH > IXSCAN | keysExamined=2 | docsExamined=2 | nReturned=2 | ms=13

=== 2) Búsqueda por número (índice único uq_ticket_numero) ===
  SIN índice:
     etapas=COLLSCAN | keysExamined=0 | docsExamined=280 | nReturned=1 | ms=0
  CON índice:
     etapas=FETCH > IXSCAN | keysExamined=1 | docsExamined=1 | nReturned=1 | ms=1

=== 3) Campo dinámico (índice wildcard idx_wildcard_campos) ===
  SIN índice:
     etapas=COLLSCAN | keysExamined=0 | docsExamined=280 | nReturned=11 | ms=2
  CON índice:
     etapas=FETCH > IXSCAN | keysExamined=11 | docsExamined=11 | nReturned=11 | ms=3

=== 4) Reporte por categoría y período (idx_categoria_creado) ===
  SIN índice:
     etapas=COLLSCAN | keysExamined=0 | docsExamined=280 | nReturned=25 | ms=2
  CON índice:
     etapas=FETCH > IXSCAN | keysExamined=25 | docsExamined=25 | nReturned=25 | ms=2

Nota: con ~280 documentos la diferencia de milisegundos es mínima; lo relevante es la cantidad de
documentos examinados (docsExamined) y la etapa del plan. Cada índice cuesta espacio y se actualiza
en cada escritura; por eso solo se crean los que respaldan los patrones de acceso reales.

ejecucion consistencia.js:

A) Asignación correcta con transacción
   FALLA la operación devuelve ok
   FALLA el ticket quedó 'asignado' a Lucía
   FALLA la carga de Lucía subió exactamente 1
   FALLA el historial registró la transición

B) Falla entre las dos escrituras: la transacción debe deshacer todo
   OK    la operación devuelve error (Transaction numbers are only allowed on a replica set member or mongos)
   OK    el ticket sigue en 'nuevo' y sin agente (rollback)
   OK    la carga de Lucía no cambió

C) Agente al tope de su capacidad: la asignación debe rechazarse sin dejar rastros
   FALLA la operación se rechaza (Transaction numbers are only allowed on a replica set member or mongos)
   OK    el ticket sigue en 'nuevo' y sin agente
   OK    la carga de Javier no superó su capacidad

D) La misma falla SIN transacción deja la base inconsistente (demostración del problema)
   OK    ticket 'asignado' a Lucía pero su carga NO subió -> inconsistencia visible

5 verificación(es) fallaron.
Datos de prueba eliminados y carga de Lucía restaurada.

ejecucion consultas.js
==== Q1 · Comparación: tickets abiertos con el SLA de resolución ya vencido ====
[
  {
    numero: 'INC-2026-000244',
    categoria: { codigo: 'HW_FALLA' },
    estado: 'en_espera',
    sla: { resolucion_limite: 2026-10-07T20:17:00.000Z }
  },
  {
    numero: 'INC-2026-000245',
    categoria: { codigo: 'HW_FALLA' },
    estado: 'en_progreso',
    sla: { resolucion_limite: 2026-10-08T12:34:00.000Z }
  },
  {
    numero: 'INC-2026-000246',
    categoria: { codigo: 'SW_ACCESO' },
    estado: 'asignado',
    sla: { resolucion_limite: 2026-10-08T07:00:00.000Z }
  },
  {
    numero: 'INC-2026-000248',
    categoria: { codigo: 'HW_FALLA' },
    estado: 'en_progreso',
    sla: { resolucion_limite: 2026-10-09T00:48:00.000Z }
  },
  {
    numero: 'INC-2026-000249',
    categoria: { codigo: 'SW_ACCESO' },
    estado: 'en_progreso',
    sla: { resolucion_limite: 2026-10-09T15:03:00.000Z }
  },
  {
    numero: 'INC-2026-000250',
    categoria: { codigo: 'RED_CONEX' },
    estado: 'en_progreso',
    sla: { resolucion_limite: 2026-10-09T15:30:00.000Z }
  },
  {
    numero: 'INC-2026-000251',
    categoria: { codigo: 'HW_FALLA' },
    estado: 'en_progreso',
    sla: { resolucion_limite: 2026-10-10T13:29:00.000Z }
  },
  {
    numero: 'INC-2026-000253',
    categoria: { codigo: 'HW_FALLA' },
    estado: 'en_progreso',
    sla: { resolucion_limite: 2026-10-12T17:26:00.000Z }
  },
  {
    numero: 'INC-2026-000254',
    categoria: { codigo: 'SW_ACCESO' },
    estado: 'en_progreso',
    sla: { resolucion_limite: 2026-10-12T15:29:00.000Z }
  },
  {
    numero: 'INC-2026-000255',
    categoria: { codigo: 'RED_CONEX' },
    estado: 'en_progreso',
    sla: { resolucion_limite: 2026-10-13T10:37:00.000Z }
  },
  {
    numero: 'INC-2026-000258',
    categoria: { codigo: 'SW_ACCESO' },
    estado: 'en_espera',
    sla: { resolucion_limite: 2026-10-14T04:04:00.000Z }
  },
  {
    numero: 'INC-2026-000259',
    categoria: { codigo: 'RED_CONEX' },
    estado: 'en_espera',
    sla: { resolucion_limite: 2026-10-13T19:05:00.000Z }
  },
  {
    numero: 'INC-2026-000260',
    categoria: { codigo: 'HW_FALLA' },
    estado: 'en_espera',
    sla: { resolucion_limite: 2026-10-14T18:06:00.000Z }
  },
  {
    numero: 'INC-2026-000262',
    categoria: { codigo: 'HW_FALLA' },
    estado: 'en_espera',
    sla: { resolucion_limite: 2026-10-17T09:10:00.000Z }
  },
  {
    numero: 'INC-2026-000263',
    categoria: { codigo: 'MANT_EDIL' },
    estado: 'en_progreso',
    sla: { resolucion_limite: 2026-10-17T10:43:00.000Z }
  },
  {
    numero: 'INC-2026-000264',
    categoria: { codigo: 'HW_FALLA' },
    estado: 'en_progreso',
    sla: { resolucion_limite: 2026-10-15T22:36:00.000Z }
  },
  {
    numero: 'INC-2026-000265',
    categoria: { codigo: 'HW_FALLA' },
    estado: 'en_progreso',
    sla: { resolucion_limite: 2026-10-17T09:20:00.000Z }
  },
  {
    numero: 'INC-2026-000266',
    categoria: { codigo: 'HW_FALLA' },
    estado: 'en_progreso',
    sla: { resolucion_limite: 2026-10-18T16:53:00.000Z }
  },
  {
    numero: 'INC-2026-000267',
    categoria: { codigo: 'SW_ACCESO' },
    estado: 'en_espera',
    sla: { resolucion_limite: 2026-10-20T02:08:00.000Z }
  },
  {
    numero: 'INC-2026-000269',
    categoria: { codigo: 'COMPRAS' },
    estado: 'asignado',
    sla: { resolucion_limite: 2026-10-22T15:21:00.000Z }
  },
  {
    numero: 'INC-2026-000271',
    categoria: { codigo: 'HW_FALLA' },
    estado: 'en_progreso',
    sla: { resolucion_limite: 2026-10-20T21:55:00.000Z }
  },
  {
    numero: 'INC-2026-000272',
    categoria: { codigo: 'HW_FALLA' },
    estado: 'en_progreso',
    sla: { resolucion_limite: 2026-10-21T15:37:00.000Z }
  },
  {
    numero: 'INC-2026-000279',
    categoria: { codigo: 'HW_FALLA' },
    estado: 'asignado',
    sla: { resolucion_limite: 2026-10-26T18:41:00.000Z }
  },
  {
    numero: 'INC-2026-000280',
    categoria: { codigo: 'HW_FALLA' },
    estado: 'en_progreso',
    sla: { resolucion_limite: 2026-10-26T19:03:00.000Z }
  }
]
==== Q2 · Comparación: tickets reabiertos o con muchos comentarios ====
[
  {
    numero: 'INC-2026-000001',
    estado: 'cerrado',
    metricas: { cant_comentarios: 5, reaperturas: 0 }
  },
  {
    numero: 'INC-2026-000003',
    estado: 'cerrado',
    metricas: { cant_comentarios: 5, reaperturas: 0 }
  },
  {
    numero: 'INC-2026-000004',
    estado: 'cerrado',
    metricas: { cant_comentarios: 4, reaperturas: 0 }
  },
  {
    numero: 'INC-2026-000011',
    estado: 'cerrado',
    metricas: { cant_comentarios: 4, reaperturas: 0 }
  },
  {
    numero: 'INC-2026-000016',
    estado: 'cerrado',
    metricas: { cant_comentarios: 5, reaperturas: 0 }
  },
  {
    numero: 'INC-2026-000019',
    estado: 'cerrado',
    metricas: { cant_comentarios: 1, reaperturas: 1 }
  },
  {
    numero: 'INC-2026-000021',
    estado: 'cerrado',
    metricas: { cant_comentarios: 5, reaperturas: 0 }
  },
  {
    numero: 'INC-2026-000022',
    estado: 'cerrado',
    metricas: { cant_comentarios: 5, reaperturas: 0 }
  },
  {
    numero: 'INC-2026-000025',
    estado: 'cerrado',
    metricas: { cant_comentarios: 4, reaperturas: 0 }
  },
  {
    numero: 'INC-2026-000030',
    estado: 'cerrado',
    metricas: { cant_comentarios: 4, reaperturas: 0 }
  }
]
==== Q3 · Operadores lógicos: urgentes y en riesgo ====
[
  {
    numero: 'INC-2026-000244',
    prioridad: 'alta',
    estado: 'en_espera',
    sla: { incumplido: true }
  },
  {
    numero: 'INC-2026-000248',
    prioridad: 'alta',
    estado: 'en_progreso',
    sla: { incumplido: true }
  },
  {
    numero: 'INC-2026-000249',
    prioridad: 'alta',
    estado: 'en_progreso',
    sla: { incumplido: true }
  },
  {
    numero: 'INC-2026-000250',
    prioridad: 'alta',
    estado: 'en_progreso',
    sla: { incumplido: true }
  },
  {
    numero: 'INC-2026-000253',
    prioridad: 'alta',
    estado: 'en_progreso',
    sla: { incumplido: true }
  },
  {
    numero: 'INC-2026-000254',
    prioridad: 'alta',
    estado: 'en_progreso',
    sla: { incumplido: true }
  },
  {
    numero: 'INC-2026-000259',
    prioridad: 'alta',
    estado: 'en_espera',
    sla: { incumplido: true }
  },
  {
    numero: 'INC-2026-000260',
    prioridad: 'alta',
    estado: 'en_espera',
    sla: { incumplido: true }
  },
  {
    numero: 'INC-2026-000264',
    prioridad: 'alta',
    estado: 'en_progreso',
    sla: { incumplido: true }
  },
  {
    numero: 'INC-2026-000271',
    prioridad: 'alta',
    estado: 'en_progreso',
    sla: { incumplido: true }
  },
  {
    numero: 'INC-2026-000279',
    prioridad: 'alta',
    estado: 'asignado',
    sla: { incumplido: true }
  },
  {
    numero: 'INC-2026-000280',
    prioridad: 'critica',
    estado: 'en_progreso',
    sla: { incumplido: true }
  }
]
==== Q4 · Atributos anidados: notebooks con falla de hardware en Sede Norte ====
5
==== Q5 · Arreglos: tickets etiquetados a la vez como 'urgente' y 'recurrente' ====
[
  {
    numero: 'INC-2026-000005',
    estado: 'cancelado',
    etiquetas: [ 'urgente', 'clase_en_curso', 'recurrente' ]
  },
  {
    numero: 'INC-2026-000029',
    estado: 'cerrado',
    etiquetas: [ 'urgente', 'recurrente' ]
  },
  {
    numero: 'INC-2026-000075',
    estado: 'cerrado',
    etiquetas: [ 'evento', 'urgente', 'recurrente' ]
  },
  {
    numero: 'INC-2026-000090',
    estado: 'cerrado',
    etiquetas: [ 'evento', 'urgente', 'recurrente' ]
  },
  {
    numero: 'INC-2026-000114',
    estado: 'cerrado',
    etiquetas: [ 'urgente', 'garantia', 'recurrente' ]
  },
  {
    numero: 'INC-2026-000145',
    estado: 'cerrado',
    etiquetas: [ 'recurrente', 'evento', 'urgente' ]
  },
  {
    numero: 'INC-2026-000167',
    estado: 'cerrado',
    etiquetas: [ 'urgente', 'recurrente' ]
  },
  {
    numero: 'INC-2026-000177',
    estado: 'cerrado',
    etiquetas: [ 'urgente', 'recurrente', 'sede_norte' ]
  },
  {
    numero: 'INC-2026-000202',
    estado: 'cerrado',
    etiquetas: [ 'clase_en_curso', 'urgente', 'recurrente' ]
  },
  {
    numero: 'INC-2026-000221',
    estado: 'cerrado',
    etiquetas: [ 'recurrente', 'urgente' ]
  },
  {
    numero: 'INC-2026-000226',
    estado: 'cerrado',
    etiquetas: [ 'recurrente', 'urgente' ]
  },
  {
    numero: 'INC-2026-000244',
    estado: 'en_espera',
    etiquetas: [ 'recurrente', 'urgente' ]
  },
  {
    numero: 'INC-2026-000249',
    estado: 'en_progreso',
    etiquetas: [ 'clase_en_curso', 'urgente', 'recurrente' ]
  }
]
==== Q6 · Proyección, orden y límite: próximos 10 vencimientos de SLA ====
[
  {
    numero: 'INC-2026-000244',
    titulo: 'Equipo muy lento al iniciar',
    estado: 'en_espera',
    agente: { nombre: 'Diego Paz' },
    sla: { resolucion_limite: 2026-10-07T20:17:00.000Z }
  },
  {
    numero: 'INC-2026-000246',
    titulo: 'Permiso a carpeta compartida',
    estado: 'asignado',
    agente: { nombre: 'Carla Benítez' },
    sla: { resolucion_limite: 2026-10-08T07:00:00.000Z }
  },
  {
    numero: 'INC-2026-000245',
    titulo: 'La PC se reinicia sola',
    estado: 'en_progreso',
    agente: { nombre: 'Lucía Ferreyra' },
    sla: { resolucion_limite: 2026-10-08T12:34:00.000Z }
  },
  {
    numero: 'INC-2026-000248',
    titulo: 'Equipo muy lento al iniciar',
    estado: 'en_progreso',
    agente: { nombre: 'Martín Olivera' },
    sla: { resolucion_limite: 2026-10-09T00:48:00.000Z }
  },
  {
    numero: 'INC-2026-000249',
    titulo: 'Permiso a carpeta compartida',
    estado: 'en_progreso',
    agente: { nombre: 'Federico Luna' },
    sla: { resolucion_limite: 2026-10-09T15:03:00.000Z }
  },
  {
    numero: 'INC-2026-000250',
    titulo: 'Wifi intermitente en biblioteca',
    estado: 'en_progreso',
    agente: { nombre: 'Javier Rossi' },
    sla: { resolucion_limite: 2026-10-09T15:30:00.000Z }
  },
  {
    numero: 'INC-2026-000251',
    titulo: 'La PC se reinicia sola',
    estado: 'en_progreso',
    agente: { nombre: 'Lucía Ferreyra' },
    sla: { resolucion_limite: 2026-10-10T13:29:00.000Z }
  },
  {
    numero: 'INC-2026-000254',
    titulo: 'Alta de usuario en el sistema académico',
    estado: 'en_progreso',
    agente: { nombre: 'Carla Benítez' },
    sla: { resolucion_limite: 2026-10-12T15:29:00.000Z }
  },
  {
    numero: 'INC-2026-000253',
    titulo: 'Equipo muy lento al iniciar',
    estado: 'en_progreso',
    agente: { nombre: 'Diego Paz' },
    sla: { resolucion_limite: 2026-10-12T17:26:00.000Z }
  },
  {
    numero: 'INC-2026-000255',
    titulo: 'Cortes de red en secretaría',
    estado: 'en_progreso',
    agente: { nombre: 'Paula Giménez' },
    sla: { resolucion_limite: 2026-10-13T10:37:00.000Z }
  }
]
==== Q7 · Aggregate: cumplimiento de SLA por categoría ====
[
  {
    _id: 'RED_CONEX',
    total: 69,
    incumplidos: 31,
    pct_incumplimiento: 44.9
  },
  {
    _id: 'HW_FALLA',
    total: 79,
    incumplidos: 20,
    pct_incumplimiento: 25.3
  },
  {
    _id: 'MANT_EDIL',
    total: 33,
    incumplidos: 7,
    pct_incumplimiento: 21.2
  },
  {
    _id: 'SW_ACCESO',
    total: 54,
    incumplidos: 11,
    pct_incumplimiento: 20.4
  },
  { _id: 'COMPRAS', total: 33, incumplidos: 5, pct_incumplimiento: 15.2 }
]
==== Q8 · Aggregate: tiempo de resolución por categoría (horas) ====
[
  {
    _id: 'MANT_EDIL',
    tickets: 31,
    min_horas: 1.3,
    max_horas: 187.8,
    tmr_horas: 36,
    desvio: 35.3
  },
  {
    _id: 'COMPRAS',
    tickets: 32,
    min_horas: 3.2,
    max_horas: 139.8,
    tmr_horas: 34.2,
    desvio: 33.8
  },
  {
    _id: 'HW_FALLA',
    tickets: 65,
    min_horas: 0.6,
    max_horas: 54,
    tmr_horas: 14,
    desvio: 13.2
  },
  {
    _id: 'SW_ACCESO',
    tickets: 48,
    min_horas: 0.9,
    max_horas: 30.4,
    tmr_horas: 8.9,
    desvio: 6.1
  },
  {
    _id: 'RED_CONEX',
    tickets: 66,
    min_horas: 0.6,
    max_horas: 31.2,
    tmr_horas: 8.5,
    desvio: 8.4
  }
]
==== Q9 · Agrupamiento con estadística: tickets creados por día de la semana ====
[
  { _id: 1, tickets: 101, pct_del_total: 36.1 },
  { _id: 2, tickets: 53, pct_del_total: 18.9 },
  { _id: 3, tickets: 42, pct_del_total: 15 },
  { _id: 4, tickets: 42, pct_del_total: 15 },
  { _id: 5, tickets: 34, pct_del_total: 12.1 },
  { _id: 6, tickets: 6, pct_del_total: 2.1 },
  { _id: 7, tickets: 2, pct_del_total: 0.7 }
]
==== Q10 · Aggregate: carga de trabajo vs. capacidad de cada agente ====
[
  {
    nombre: 'Diego Paz',
    capacidad_maxima: 8,
    carga_actual: 4,
    ocupacion_pct: 50
  },
  {
    nombre: 'Martín Olivera',
    capacidad_maxima: 8,
    carga_actual: 4,
    ocupacion_pct: 50
  },
  {
    nombre: 'Javier Rossi',
    capacidad_maxima: 4,
    carga_actual: 2,
    ocupacion_pct: 50
  },
  {
    nombre: 'Federico Luna',
    capacidad_maxima: 6,
    carga_actual: 3,
    ocupacion_pct: 50
  },
  {
    nombre: 'Carla Benítez',
    capacidad_maxima: 10,
    carga_actual: 4,
    ocupacion_pct: 40
  },
  {
    nombre: 'Paula Giménez',
    capacidad_maxima: 5,
    carga_actual: 2,
    ocupacion_pct: 40
  },
  {
    nombre: 'Lucía Ferreyra',
    capacidad_maxima: 10,
    carga_actual: 3,
    ocupacion_pct: 30
  },
  {
    nombre: 'Nicolás Aguirre',
    capacidad_maxima: 8,
    carga_actual: 2,
    ocupacion_pct: 25
  },
  {
    nombre: 'Romina Castro',
    capacidad_maxima: 8,
    carga_actual: 1,
    ocupacion_pct: 12
  }
]
==== Q11 · Compleja ($lookup + $unwind): satisfacción por agente y por habilidad ====
[
  {
    encuestas: 31,
    agente: 'Paula Giménez',
    nivel: 2,
    sede: 'Sede Centro',
    puntaje_prom: 2.39
  },
  {
    encuestas: 14,
    agente: 'Javier Rossi',
    nivel: 2,
    sede: 'Sede Norte',
    puntaje_prom: 2.93
  },
  {
    encuestas: 9,
    agente: 'Carla Benítez',
    nivel: 1,
    sede: 'Sede Centro',
    puntaje_prom: 3.89
  },
  {
    encuestas: 21,
    agente: 'Federico Luna',
    nivel: 3,
    sede: 'Sede Centro',
    puntaje_prom: 4.14
  },
  {
    encuestas: 20,
    agente: 'Lucía Ferreyra',
    nivel: 1,
    sede: 'Sede Centro',
    puntaje_prom: 4.15
  },
  {
    encuestas: 23,
    agente: 'Martín Olivera',
    nivel: 2,
    sede: 'Sede Sur',
    puntaje_prom: 4.17
  },
  {
    encuestas: 18,
    agente: 'Romina Castro',
    nivel: 1,
    sede: 'Sede Norte',
    puntaje_prom: 4.17
  },
  {
    encuestas: 7,
    agente: 'Nicolás Aguirre',
    nivel: 1,
    sede: 'Sede Sur',
    puntaje_prom: 4.29
  },
  {
    encuestas: 18,
    agente: 'Diego Paz',
    nivel: 2,
    sede: 'Sede Norte',
    puntaje_prom: 4.44
  }
]
==== Q12 · Búsqueda dinámica (usa el índice wildcard): fallas de red en la VLAN 100 ====
[
  {
    numero: 'INC-2026-000019',
    estado: 'cerrado',
    campos_personalizados: { equipos_afectados: 5, tipo_falla: 'wifi' }
  },
  {
    numero: 'INC-2026-000053',
    estado: 'cerrado',
    campos_personalizados: { equipos_afectados: 5, tipo_falla: 'sin_enlace' }
  },
  {
    numero: 'INC-2026-000077',
    estado: 'cerrado',
    campos_personalizados: { equipos_afectados: 2, tipo_falla: 'intermitente' }
  },
  {
    numero: 'INC-2026-000102',
    estado: 'cerrado',
    campos_personalizados: { equipos_afectados: 12, tipo_falla: 'sin_enlace' }
  },
  {
    numero: 'INC-2026-000126',
    estado: 'cerrado',
    campos_personalizados: { equipos_afectados: 1, tipo_falla: 'intermitente' }
  }
]

## 4. Índices y análisis de rendimiento

Archivo: `consultas/indices.js`.

| Índice | Campos | Patrón de acceso que respalda | Consultas |
| --- | --- | --- | --- |
| `idx_bandeja_agente` | `agente.agente_id`, `estado`, `sla.resolucion_limite` | Bandeja priorizada del agente (igualdad, igualdad, orden) | Q6 |
| `uq_ticket_numero` | `numero` (único) | Búsqueda por número; evita duplicados | RF-02 |
| `idx_wildcard_campos` | `campos_personalizados.$**` | Búsqueda por campos que varían según la categoría | Q12 |
| `idx_categoria_creado` | `categoria.codigo`, `creado` | Reportes por categoría y período | Q7, Q8 |
| `uq_agente_email`, `uq_cliente_email` | `email` (únicos) | Integridad | n/a |

**Costo:** cada índice ocupa espacio y se actualiza en cada inserción o modificación. Por eso solo se crearon los que respaldan patrones de acceso reales. *COMPLETAR con los tamaños de índice que imprime `indices.js`.*

**Análisis con `explain("executionStats")`** (`consultas/explain.js`, compara la misma consulta forzando recorrido completo y forzando el índice):

| Consulta | Sin índice: etapa / docsExamined | Con índice: etapa / keysExamined / docsExamined | nReturned |
| --- | --- | --- | --- |
| Bandeja del agente | *COMPLETAR* | *COMPLETAR* | *COMPLETAR* |
| Por número de ticket | *COMPLETAR* | *COMPLETAR* | *COMPLETAR* |
| Campo dinámico (VLAN) | *COMPLETAR* | *COMPLETAR* | *COMPLETAR* |
| Categoría y período | *COMPLETAR* | *COMPLETAR* | *COMPLETAR* |

**Interpretación:** *COMPLETAR con 3 o 4 líneas propias.* Qué mirar: sin índice la etapa es `COLLSCAN` y `docsExamined` es igual al total de la colección (280); con índice debería aparecer `IXSCAN` y `docsExamined` cercano a `nReturned`. Con tan pocos documentos la diferencia de milisegundos es mínima y la consigna no la exige; lo que importa es la etapa del plan y los documentos examinados.

## 5. Consistencia y transacciones (primeras pruebas)

**Caso:** asignar un ticket a un agente (RF-06). Modifica dos documentos: el ticket (`agente`, `estado`, `historial`) y el agente (`carga_actual`).

**Qué puede fallar sin transacción:** si se completa solo la primera escritura, el ticket queda asignado a un agente cuya carga no lo refleja y el agente puede recibir más tickets que su capacidad; si se completa solo la segunda, el agente queda con una carga que no corresponde a ningún ticket.

**Solución:** transacción multidocumento (requiere replica set). El control de cupo se hace dentro de la transacción con `$expr: { $lt: ["$carga_actual", "$capacidad_maxima"] }`, de modo que dos asignaciones simultáneas no superen la capacidad.

**Pruebas** (`consultas/consistencia.js`):

| Escenario | Resultado esperado |
| --- | --- |
| A. Asignación correcta | Ticket `asignado`, carga +1, historial con la transición |
| B. Falla simulada entre las dos escrituras | Rollback: ticket sigue `nuevo` y sin agente, carga sin cambios |
| C. Agente en su capacidad máxima | Se rechaza; ticket y carga sin cambios |
| D. Misma falla sin transacción | Ticket `asignado` pero carga sin cambiar (inconsistencia que demuestra el problema) |

El script borra sus tickets de prueba y restaura la carga al terminar.

**Evidencia de ejecución:** *COMPLETAR con la salida de `mongosh sentinel --file consultas/consistencia.js`.*

## 6. Lista de evidencias a adjuntar
- [ ] Salida de `cargar_datos.py`
- [ ] Salida de `consultas.js`
- [ ] Salida de `indices.js` y de `explain.js`
- [ ] Salida de `consistencia.js`

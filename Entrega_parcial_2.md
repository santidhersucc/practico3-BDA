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

**Evidencia de ejecución:** *COMPLETAR con la salida de `python scripts/cargar_datos.py`.*

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

**Evidencia de ejecución:** *COMPLETAR con la salida de `mongosh sentinel --file consultas/consultas.js` y comprobar cada resultado contra la columna "Esperado".*

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

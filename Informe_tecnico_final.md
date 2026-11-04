# Sentinel · Informe técnico final

**Trabajo Práctico Integrador · Base de Datos Aplicada** · Noviembre 2026

**Integrantes:** Enzo Parra, Santiago Dhers, Tomas Vogt, Santino Vazquez de Novoa

## 1. Resumen

Sentinel es una plataforma de gestión de incidentes de soporte para una organización con varias sedes. Se implementó sobre MongoDB con cinco colecciones, una API REST con capa de repositorios (FastAPI y PyMongo), un caso de consistencia resuelto con transacciones multidocumento, un módulo de análisis en Python y un entorno reproducible con Docker Compose. Este informe documenta el problema, el modelo documental y sus justificaciones, las consultas, los índices, la estrategia de consistencia, la API, el análisis de datos y el despliegue.

## 2. Problema, actores y requerimientos

Una organización con varias sedes recibe pedidos de soporte por correo, chat y planillas, y no puede responder con rapidez ni medir cómo lo hace. Cada tipo de pedido necesita datos distintos: un caso de hardware pide número de inventario y síntoma; uno de red, sede, VLAN y equipos afectados; uno de compras, centro de costo e importe. Nada los unifica, y eso produce cuatro problemas: no hay trazabilidad de quién tocó cada pedido, no hay plazos comprometidos (SLA), la carga de trabajo no se reparte y faltan métricas para decidir.

| Actor | Qué hace en el sistema |
| --- | --- |
| Solicitante | Crea tickets, comenta, consulta su estado y valora la atención |
| Agente de soporte | Toma tickets, los resuelve, comenta y cambia estados |
| Supervisor | Asigna y reasigna, controla la carga y los vencimientos de SLA |
| Administrador | Define el catálogo de servicios: categorías, campos, SLA y flujos |
| Sistema | Calcula plazos, marca incumplimientos y numera los tickets atómicamente |

| Id | Requerimiento funcional | Estado en la implementación |
| --- | --- | --- |
| RF-01 | Crear un ticket validando los campos personalizados contra su categoría | Implementado en la API |
| RF-02 | Obtener un ticket por número (INC-2026-000142) con todo su contexto | Implementado (se usa el número, no el `_id`) |
| RF-03 | Listar tickets con filtros (estado, prioridad, agente) y paginación | Implementado |
| RF-04 | Actualizar datos y cambiar estado respetando las transiciones permitidas | Implementado |
| RF-05 | Comentar actualizando contadores y SLA de primera respuesta atómicamente | Implementado |
| RF-06 | Asignar un ticket verificando la capacidad máxima del agente (transacción) | Implementado |
| RF-07 | Calcular los límites de SLA al crear y registrar el cumplimiento | Implementado |
| RF-08 | Administrar categorías (campos, transiciones, tiempos SLA) | No expuesto por API: las categorías se gestionan con los scripts de carga |
| RF-09 | Eliminar un ticket solo en estado nuevo o cancelado | Implementado |
| RF-10 | Registrar la encuesta de satisfacción al cerrar | Sin endpoint: la encuesta está en los datos de prueba y se usa en consultas y análisis |

## 3. Modelo documental

### 3.1 Por qué un modelo documental

Un ticket es un agregado que casi siempre se lee y se modifica completo, y cuya parte variable depende de la categoría. Esas dos propiedades son las que más favorecen al modelo documental. La justificación no es que MongoDB sea mejor en general, sino que este dominio tiene la forma para la que fue pensado.

| Aspecto | Diseño relacional | Diseño documental (Sentinel) |
| --- | --- | --- |
| Campos variables por categoría | Tabla EAV o muchas columnas NULL | Subdocumento `campos_personalizados` con tipos nativos |
| Alta de una categoría nueva | Metadatos nuevos y migraciones de esquema | Un documento nuevo en `categorias`, sin migrar tickets |
| Leer un ticket completo | Join entre unas 5 tablas | Un único `findOne` |
| Evolución del modelo | Coordinar esquema y código | Campo `schema_version` en cada documento |

### 3.2 Colecciones

| Colección | Docs | Rol y estructura |
| --- | --- | --- |
| `tickets` | 280 | Entidad principal. Embebe comentarios, historial, adjuntos, sla, metricas, satisfaccion y campos\_personalizados |
| `categorias` | 5 | Plantillas de servicio: campos personalizados, SLA por prioridad y transiciones de estado permitidas. Su `_id` es el código natural (HW\_FALLA) |
| `agentes` | 10 | Personal de soporte con habilidades, turno, `capacidad_maxima` y `carga_actual` (valor calculado) |
| `clientes` | 60 | Solicitantes. Embebe sus equipos (1 a 5 por persona) |
| `contadores` | 1 | Un documento por año para la numeración atómica (valor actual: 280) |

Obligatorios en tickets: numero, titulo, descripcion, categoria, prioridad, estado, solicitante, sla, comentarios, historial, metricas, creado, actualizado y schema\_version. Opcionales: agente (hasta ser asignado), campos\_personalizados, etiquetas, adjuntos, satisfaccion, resuelto\_en y sla.primera\_respuesta\_en.

### 3.3 Ejemplos de documentos (sintaxis de mongosh)

```javascript
// tickets (recortado)
{
  _id: ObjectId('66f1a2b3c4d5e6f7a8b9c0d1'),
  numero: 'INC-2026-000142',
  titulo: 'La notebook no enciende tras un corte de luz',
  categoria: { codigo: 'HW_FALLA', nombre: 'Falla de hardware' },
  prioridad: 'alta', estado: 'en_progreso',
  solicitante: { cliente_id: ObjectId('66f1a2b3c4d5e6f7a8b9b001'), nombre: 'Marta Quiroga', sede: 'Sede Norte' },
  agente: { agente_id: ObjectId('66f1a2b3c4d5e6f7a8b9a003'), nombre: 'Diego Paz' },
  campos_personalizados: { equipo: { inventario: 'INV-004512', tipo: 'notebook', marca: 'Lenovo' }, sintoma: 'no_enciende' },
  etiquetas: ['corte_de_luz', 'notebook'],
  sla: { resolucion_limite: ISODate('2026-10-19T20:12:00Z'), primera_respuesta_en: ISODate('2026-10-19T12:40:00Z'), incumplido: false },
  comentarios: [ { autor: { tipo: 'agente', nombre: 'Diego Paz' }, texto: 'Voy a retirar el equipo.', fecha: ISODate('2026-10-19T12:40:00Z') } ],
  historial: [ { fecha: ISODate('2026-10-19T12:12:00Z'), tipo: 'estado', de: null, a: 'nuevo' } ],
  metricas: { cant_comentarios: 1, reaperturas: 0 },
  creado: ISODate('2026-10-19T12:12:00Z'), schema_version: 1
}

// categorias (recortado)
{
  _id: 'HW_FALLA', nombre: 'Falla de hardware', activa: true,
  campos_personalizados: [ { clave: 'equipo.inventario', tipo: 'string', obligatorio: true },
                           { clave: 'sintoma', tipo: 'enum', opciones: ['no_enciende', 'lento', 'ruido'] } ],
  sla: { alta: { respuesta_min: 60, resolucion_min: 480 } /* critica, media y baja igual */ },
  transiciones: { nuevo: ['asignado', 'cancelado'], resuelto: ['cerrado', 'en_progreso'] /* ... */ }
}
```

### 3.4 Embeber o referenciar

**Se embebe** lo que se lee y se modifica junto con el ticket y está acotado en la práctica: comentarios, historial, adjuntos, sla y metricas. La interfaz necesita todo el contexto en una vista y se resuelve con un solo `findOne`. Los arreglos crecen a decenas de elementos, no a miles, así que no hay riesgo de acercarse al límite de 16 MB. En clientes se embeben los equipos por la misma razón (pocos, y se leen con el solicitante).

**Se referencia** lo que tiene vida propia: la categoría (por código natural), el solicitante y el agente. Así la definición de un servicio o sus SLA pueden cambiar sin reescribir los tickets históricos, que conservan sus límites ya calculados.

### 3.5 Patrones aplicados

- **Referencia extendida:** el ticket guarda, además del ObjectId, nombre, email y sede del solicitante y el nombre del agente. Evita `$lookup` al listar bandejas. El costo es que un cambio posterior no se propaga, lo que además sirve como registro histórico.
- **Valor calculado:** `carga_actual` en agentes y `metricas` en tickets se actualizan al escribir, para no contar documentos en cada lectura.
- **Atributos polimórficos:** `campos_personalizados` varía según la categoría.
- **Versionado de esquema:** `schema_version` prepara la convivencia con cambios futuros.
- **Contador atómico:** la numeración INC-AAAA-NNNNNN sale de un `findOneAndUpdate` con `$inc`.

## 4. Implementación y carga de datos

Tres scripts reproducibles: `generar_datos.py` (semilla fija SEED = 42), `verificar_datos.py` (integridad sin necesitar MongoDB) y `cargar_datos.py`, que borra y recrea las colecciones con validadores `$jsonSchema` (tickets y agentes), inserta los archivos NDJSON de `data/` y verifica los conteos y los invariantes.

| Colección | Documentos |
| --- | --- |
| tickets | 280 (período jul–oct 2026) |
| clientes | 60 |
| agentes | 10 (uno inactivo) |
| categorias | 5 |
| contadores | 1 |
| **Total** | **356** |

**Variedad y casos límite:** campos personalizados distintos por categoría; opcionales ausentes (garantia\_vigente, proveedor, etiquetas, adjuntos, agente, satisfaccion); cancelados sin agente; tickets reabiertos y sin comentarios; descripciones extensas; tickets abiertos con el SLA vencido; un agente inactivo. Los datos incluyen patrones deliberados para el análisis: el 36,1 % de los tickets se crea los lunes y RED\_CONEX incumple el SLA en el 44,9 % de los casos.

**Verificaciones al cargar:** el conteo de cada colección coincide con su archivo; el contador es igual al último número de ticket; todo ticket con agente referencia un agente existente; la `carga_actual` de cada agente es igual a sus tickets abiertos.

**Reinicializar:** volver a ejecutar `cargar_datos.py` (borra y recarga todo) y luego `indices.js`, porque al borrar las colecciones se pierden los índices.

## 5. Consultas

Se implementaron 12 consultas en `consultas/consultas.js`, cada una con objetivo, operadores y resultado esperado (la evidencia de ejecución está en la entrega parcial 2).

| Id | Tipo | Pregunta del dominio | Resultado |
| --- | --- | --- | --- |
| Q1 | Comparación (`$in`, `$lt`) | ¿Qué tickets abiertos ya vencieron su SLA de resolución? | 24 tickets |
| Q2 | Comparación (`$gt`, `$gte` dentro de `$or`) | ¿Qué tickets fueron reabiertos o tienen 4 o más comentarios? | 80 tickets |
| Q3 | Operadores lógicos (`$in`, `$or`) | Lista de intervención inmediata: prioridad crítica o alta, abiertos y con SLA incumplido o sin agente | 12 tickets |
| Q4 | Atributos anidados (3 niveles) | ¿Cuántas notebooks con falla de hardware hay en Sede Norte? | 5 |
| Q5 | Arreglos (`$all`) | ¿Qué tickets están etiquetados como urgente y recurrente? | 13 tickets |
| Q6 | Proyección, orden y límite | Próximos 10 vencimientos de SLA entre los abiertos | 10 documentos |
| Q7 | aggregate (`$group`, `$cond`) | Cumplimiento de SLA por categoría | RED\_CONEX 44,9 %, HW\_FALLA 25,3 %, MANT\_EDIL 21,2 %, SW\_ACCESO 20,4 %, COMPRAS 15,2 % |
| Q8 | aggregate (`$dateDiff`, `$stdDevPop`) | Tiempo de resolución por categoría, con mínimo, máximo y desvío | Media: MANT\_EDIL 36,0 h, COMPRAS 34,2 h, HW\_FALLA 14,0 h, SW\_ACCESO 8,9 h, RED\_CONEX 8,5 h |
| Q9 | Agrupamiento con estadística (`$isoDayOfWeek`, `$setWindowFields`) | ¿Qué día de la semana se crean más tickets? | Lunes: 101 tickets (36,1 %) |
| Q10 | aggregate (`$project`) | Carga de trabajo contra capacidad de cada agente | Ocupación entre 12 % y 50 % |
| Q11 | Compleja (`$lookup`, `$unwind`) | Satisfacción por agente con su nivel y sede | Los más bajos: Paula Giménez 2,39 y Javier Rossi 2,93 |
| Q12 | Búsqueda dinámica (índice wildcard) | Fallas de red en la VLAN 100 | 11 tickets |

Q11 es la única que necesita `$lookup`: pide datos del agente (nivel y sede) que no están copiados en el ticket. Es el costo, explícito, de haber referenciado a los agentes en lugar de embeberlos.

## 6. Índices y análisis de rendimiento

| Índice | Campos | Patrón de acceso | Consulta |
| --- | --- | --- | --- |
| `idx_bandeja_agente` | agente.agente\_id, estado, sla.resolucion\_limite | Bandeja priorizada del agente. Igualdad, igualdad, orden (regla ESR) | Q6 y listado de la API |
| `uq_ticket_numero` (único) | numero | Búsqueda puntual y garantía de que no se repite la numeración | GET /tickets/{numero} |
| `idx_wildcard_campos` | `campos_personalizados.$**` | Las rutas varían por categoría y no se pueden indexar una a una | Q12 |
| `idx_categoria_creado` | categoria.codigo, creado | Reportes por categoría y período | Q7, Q8 |
| `uq_agente_email`, `uq_cliente_email` (únicos) | email | Integridad de correos | n/a |

Se ejecutó `explain('executionStats')` forzando el recorrido completo con `hint({ $natural: 1 })` y luego con el índice correspondiente:

| Consulta | Sin índice | Con índice | nReturned |
| --- | --- | --- | --- |
| Bandeja del agente | SORT > COLLSCAN, 280 docs | FETCH > IXSCAN, 2 claves, 2 docs | 2 |
| Por número de ticket | COLLSCAN, 280 docs | FETCH > IXSCAN, 1 clave, 1 doc | 1 |
| Campo dinámico (VLAN 100) | COLLSCAN, 280 docs | FETCH > IXSCAN, 11 claves, 11 docs | 11 |
| Categoría y período | COLLSCAN, 280 docs | FETCH > IXSCAN, 25 claves, 25 docs | 25 |

**Interpretación.** Sin índice MongoDB lee los 280 documentos en todas las consultas. Con índice, docsExamined es igual a nReturned: no se lee nada de más. En la bandeja del agente además desaparece la etapa SORT, porque el índice ya entrega los resultados ordenados. Con 280 documentos la diferencia en milisegundos es mínima; lo relevante es el plan y la cantidad de documentos examinados.

**Costo.** La colección tickets ocupa 445.179 bytes y sus cinco índices (con `_id_`) suman 106.496 bytes, alrededor del 24 % del tamaño de los datos. Cada índice ocupa espacio y se actualiza en cada escritura. Por eso no se indexaron campos de baja selectividad como prioridad, y solo se crearon índices que respaldan consultas reales o restricciones de unicidad.

## 7. Consistencia y transacciones

**Operación crítica: asignar un ticket a un agente.** Modifica dos documentos de dos colecciones: en tickets, el subdocumento agente, el estado y el historial; en agentes, el incremento de `carga_actual`, que no debe superar `capacidad_maxima`.

**Qué podría pasar sin transacción.** Si se actualiza el ticket y falla el agente, el ticket figura asignado a alguien cuya carga no lo refleja, y ese agente podría recibir más trabajo que su capacidad. Si se incrementa la carga y falla el ticket, el agente queda con una carga fantasma que bloquea su cupo.

**Solución: transacción multidocumento** (`session.with_transaction` de PyMongo) sobre un replica set de un miembro (rs0), porque una instancia independiente no admite transacciones. El control de cupo va dentro del filtro del update del agente (`$expr` con `$lt` entre carga\_actual y capacidad\_maxima, junto con `$inc`), no en un if previo, de modo que MongoDB evalúa la condición y aplica el incremento de forma atómica. El mismo mecanismo se usa al reasignar (+1 al nuevo y −1 al anterior), al resolver o cancelar (−1) y al reabrir (+1 con control de cupo). Si cualquier paso falla se lanza un error de dominio, la transacción se aborta y no queda nada a medias.

**Operaciones atómicas sin transacción.** Comentar combina `$push`, `$inc` y `$set` en un único update sobre el ticket. La numeración usa `findOneAndUpdate` con `$inc` sobre contadores. Los cambios de estado que no tocan la carga (por ejemplo asignado a en\_progreso) usan un solo update con el estado esperado en el filtro.

**Pruebas del comportamiento ante errores** (`consistencia.js` en mongosh y `test_consistencia.py` contra la API):

| Escenario | Resultado verificado |
| --- | --- |
| A. Asignación correcta | Commit: el ticket queda asignado, la carga sube exactamente 1 y el historial registra la transición |
| B. Falla simulada entre las dos escrituras | Rollback: el ticket sigue en nuevo y sin agente, y la carga no cambió |
| C. Agente en su capacidad máxima | Se rechaza sin dejar rastros: ticket sin cambios y carga sin superar el tope |
| D. La misma falla sin transacción | Demostración del problema: el ticket queda asignado pero la carga no sube |

**Concurrencia.** Diez asignaciones simultáneas por el último cupo de un agente: entra solo una. Cinco pedidos simultáneos para el mismo ticket: se asigna una sola vez. Cada test verifica al final que `carga_actual` coincida con los tickets abiertos de cada agente.

## 8. API y repositorios

La API está en Python con FastAPI, Pydantic 2 y PyMongo. Tiene tres capas: el **router** solo lee parámetros, llama al servicio y elige el código HTTP; el **servicio** aplica las reglas de negocio (SLA, campos personalizados, transiciones, carga de agentes, transacciones) sin saber nada de HTTP; los **repositorios**, uno por colección, son los únicos que ejecutan consultas. Todas las funciones de repositorio aceptan `session=None`: sueltas funcionan solas, y dentro de una transacción el servicio les pasa la sesión.

| Método | Ruta | Función | Respuestas |
| --- | --- | --- | --- |
| POST | /tickets | Crear un ticket | 201, 422 |
| GET | /tickets/{numero} | Obtener un ticket | 200, 404, 422 |
| GET | /tickets?estado=&prioridad=&agente\_id=&page=&size= | Listar con filtros y paginación | 200, 422 |
| PATCH | /tickets/{numero} | Editar título, descripción, prioridad o etiquetas | 200, 404, 409, 422 |
| DELETE | /tickets/{numero} | Eliminar (solo nuevo o cancelado) | 204, 404, 409 |
| PATCH | /tickets/{numero}/estado | Cambiar estado respetando las transiciones | 200, 404, 409, 422 |
| POST | /tickets/{numero}/comentarios | Agregar un comentario | 201, 404, 409, 422 |
| POST | /tickets/{numero}/asignar | Asignar o reasignar (transacción) | 200, 404, 409, 422 |
| GET | /health | Verifica la conexión a MongoDB | 200, 503 |

**Validación en dos niveles.** Pydantic valida el formato (tipos, obligatorios, valores permitidos, ObjectId, campos desconocidos rechazados) y responde 422. El servicio valida lo que depende de la base: que la categoría exista y esté activa, que los campos personalizados cumplan su definición, que la transición esté permitida y que el agente tenga cupo. El estado, el número, el SLA, las métricas y el historial no se reciben: los calcula la API.

**Errores.** Todos tienen el formato `{ error, detalle }`: NoEncontrado responde 404, Conflicto 409 (transición no permitida, agente sin cupo, borrar un ticket abierto, clave duplicada), Validacion 422 y MongoDB sin respuesta 503. Un ticket cambiado por otro request entre la lectura y la escritura no matchea el filtro con el estado esperado y produce un 409, no un dato pisado.

**Pruebas.** 53 tests automatizados con pytest (38 de CRUD, validaciones y errores; 15 de consistencia y concurrencia) sobre una base descartable `sentinel_test` que se crea, se reinicia antes de cada test y se borra al final, sin tocar la base `sentinel`.

## 9. Análisis de datos

El notebook `analisis/analisis_sentinel.ipynb` se conecta a MongoDB, recupera los datos con proyección, los prepara con Pandas y calcula tres indicadores con sus gráficos (Matplotlib).

| Indicador | Gráfico | Resultado principal |
| --- | --- | --- |
| Incumplimiento del SLA por categoría | Barras | RED\_CONEX incumple el 44,9 % (31 de 69), casi el doble que HW\_FALLA (25,3 %). Su satisfacción promedio es 2,44 contra 4,07 a 4,30 en las demás |
| Tiempo de resolución por categoría | Diagrama de cajas | RED\_CONEX es la más rápida (media 8,5 h, mediana 5,4 h); MANT\_EDIL y COMPRAS son las más lentas (36,0 h y 34,2 h) pero tienen plazos más largos |
| Trabajo atendido por unidad de capacidad | Barras horizontales | Paula Giménez (8,6) y Javier Rossi (8,5) atendieron mucho más que el resto (1,6 a 5,8) |

**Interpretación.** Tardar mucho no explica incumplir: RED\_CONEX es la categoría más rápida y la que más incumple, porque es la que promete plazos más exigentes (1, 4, 12 y 24 horas según la prioridad, contra 48 o 72 horas para prioridad media en MANT\_EDIL y COMPRAS). Ningún agente supera hoy el 50 % de ocupación, así que el problema no es una sobrecarga actual sino la concentración: solo Paula Giménez y Javier Rossi tienen la habilidad RED\_CONEX, son los de menor capacidad (5 y 4) y los de mayor incumplimiento (37,2 % y 47,1 %). Javier incumple 15 de 26 tickets de red pero 1 de 8 de hardware, lo que sugiere que el problema acompaña a la categoría y no a la persona. Es una asociación en estos datos, no una prueba de causalidad.

**Recomendación.** Redistribuir y ampliar, no contratar: (1) habilitar RED\_CONEX en al menos dos agentes más, empezando por los de menor uso relativo de su capacidad (Carla Benítez y Nicolás Aguirre, 1,6 tickets por unidad de capacidad); (2) dedicar a Javier Rossi a red, derivando sus 8 tickets de hardware a agentes con esa habilidad y capacidad libre; (3) revisar si los plazos de RED\_CONEX son realistas. Los datos de prueba se generaron con patrones deliberados, por lo que la conclusión vale para este conjunto y no se extrapola a una operación real.

## 10. Despliegue con Docker Compose

| Servicio | Contenedor | Descripción |
| --- | --- | --- |
| mongo | sentinel-mongo | MongoDB 7.0 como replica set rs0 de un miembro, inicializado por el healthcheck. Datos en el volumen `sentinel_mongo_data`. Publicado en 127.0.0.1:27017 |
| api | sentinel-api | API FastAPI (Python 3.12). Espera a que mongo esté healthy y se conecta por el nombre del servicio (`mongodb://mongo:27017/?replicaSet=rs0`), no por localhost. Publicada en 127.0.0.1:8000 |

La configuración se toma de variables de entorno (MONGO\_PORT, API\_PORT, MONGO\_DB, ANIO\_NUMERACION) con valores por defecto, y el archivo `.env.example` las documenta sin credenciales: el MongoDB local no usa autenticación y `.env` está en `.gitignore`.

```bash
docker compose up -d --build                                                     # iniciar
docker compose exec api python scripts/cargar_datos.py                           # cargar datos
docker compose exec mongo mongosh sentinel --quiet --file /consultas/indices.js  # crear índices
docker compose exec api python -m pytest api/tests -v                            # 53 tests
docker compose down                                                              # detener (los datos se conservan)
docker compose down -v                                                           # detener y borrar los datos
```

## 11. Decisiones y limitaciones

- **Huecos en la numeración.** El número se obtiene del contador antes de insertar el ticket; si la inserción fallara, ese número quedaría sin usar. Se acepta: la garantía importante es que no se repita. Incluir el contador en la transacción serializaría todas las altas sobre un mismo documento.
- **Referencia extendida desactualizable.** Si un cliente cambia su email, los tickets anteriores conservan el anterior, lo que es razonable como registro del momento del reporte.
- **Lecturas fuera de la transacción.** El servicio lee antes de abrir la transacción para validar y armar mensajes de error, pero las escrituras repiten las condiciones en sus filtros, así que un cambio concurrente produce un 409 y no un dato incorrecto.
- **Replica set de un solo miembro.** Habilita las transacciones pero no ofrece tolerancia a fallos; en producción serían al menos tres miembros.
- **Alcance.** No se expone la administración de categorías (RF-08) ni el registro de la encuesta (RF-10) por API, y no hay autenticación; la consigna solo exige el CRUD de la entidad principal.
- **Datos sintéticos.** No hay tickets en estado nuevo, así que la rama de Q3 que busca tickets sin agente no tiene coincidencias en los datos iniciales (se verificó que funciona creando un ticket por la API).

## 12. Conclusiones

El modelo documental resultó adecuado para este dominio. Tener el ticket como agregado permitió leerlo y modificarlo completo con una sola operación, los campos personalizados polimórficos evitaron un esquema rígido o una tabla EAV, y agregar una categoría nueva no requiere migrar nada.

El diseño también tiene compromisos, y quedaron a la vista en el proyecto. La referencia extendida duplica datos y no se actualiza sola. Consultas que cruzan colecciones, como la satisfacción por agente (Q11), necesitan `$lookup`. Los valores calculados como `carga_actual` exigen mantenerlos consistentes en cada escritura, y eso obligó a usar transacciones multidocumento, que a su vez requieren un replica set. Los índices aceleran lecturas pero cuestan espacio y escrituras, por lo que se limitaron a los patrones de acceso reales.

La solución cumple el ciclo completo: base poblada y reproducible, consultas y agregaciones del dominio, índices justificados con explain, un caso de consistencia probado ante fallos y concurrencia, una API con repositorios y 53 tests, un análisis que termina en una recomendación concreta (reforzar la atención de redes) y un entorno que se levanta con Docker Compose.

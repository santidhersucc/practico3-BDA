# Sentinel: Gestión de incidentes con modelo documental (Entrega Parcial 1)

**Fecha:** Octubre 2026
**Proyecto:** Trabajo Práctico Integrador MongoDB - Base de Datos Aplicada
**Integrantes:** Enzo Parra, Santiago Dhers, Tomas Vogt, Santino Vazquez de Noova

---

## 1. Resumen de la propuesta

**Sentinel** es una plataforma de gestión de incidentes y solicitudes de soporte para una organización con varias sedes, construida sobre MongoDB, donde cada categoría de incidente define sus propios campos, flujo de estados y plazos de atención (SLA). El modelo se adapta a nuevos tipos de ticket sin migraciones de esquema, que es exactamente el tipo de problema donde una base documental aporta valor real.

Lo que distingue a la propuesta:
- **Plantillas dinámicas:** La colección `categorias` define campos personalizados, validaciones, SLA y transiciones permitidas; cada ticket hereda esa definición.
- **El ticket como agregado:** Comentarios, historial, adjuntos y encuesta de satisfacción viven dentro del documento, por lo que un ticket completo se lee y se modifica en una sola operación.
- **Consistencia con criterio:** La asignación de un ticket respeta la capacidad del agente mediante una transacción multidocumento; el resto de las operaciones se resuelve con operaciones atómicas sobre un único documento.
- **Análisis con intención:** Los datos de prueba se generan con patrones deliberados (picos semanales, una categoría con SLA deficitario) para que las conclusiones del módulo de análisis sean verificables y deriven en una recomendación concreta.

## 2. Problema y actores

Una organización con varias sedes recibe pedidos de soporte por correo, chat y planillas, y no puede responder con rapidez ni medir cómo lo hace, porque cada tipo de pedido necesita datos distintos y nada los unifica. Un caso de hardware pide número de inventario y síntoma; uno de red, sede, VLAN y equipos afectados; uno de mantenimiento edilicio, ubicación y fotos; uno de compras, centro de costo e importe.

Esa dispersión produce cuatro problemas concretos:
- No hay **trazabilidad**: nadie sabe quién tocó un pedido ni cuándo cambió de estado.
- No hay **plazos comprometidos**: no existe un SLA por prioridad y categoría, ni alertas de vencimiento.
- La **carga de trabajo** no se reparte: unos agentes se saturan mientras otros esperan.
- No hay **métricas** para decidir: tiempos de resolución, incumplimientos y satisfacción quedan sin medir.

**Actores involucrados:**
| Actor | Rol | Qué hace en el sistema |
| --- | --- | --- |
| Solicitante | Usuario final (docente, administrativo, estudiante) | Crea tickets, comenta, consulta su estado y valora la atención |
| Agente de soporte | Técnico de primer o segundo nivel | Toma tickets, los resuelve, comenta y cambia estados |
| Supervisor | Coordina el equipo | Asigna y reasigna, controla la carga y los vencimientos de SLA |
| Administrador | Define el catálogo de servicios | Crea y edita categorías, campos personalizados, SLA y flujos |
| Sistema | Proceso automático | Calcula plazos, marca incumplimientos y numera los tickets atómicamente |

## 3. Justificación del paradigma: Por qué un modelo documental

Un ticket es un **agregado** que casi siempre se lee y se modifica completo, y cuya parte variable depende de la categoría; esas dos propiedades son las que más favorecen al modelo documental. En SQL, representar lo mismo exige fragmentar el ticket en varias tablas y recomponerlo con costosos `JOINs` en cada lectura.

| Aspecto | Diseño relacional | Diseño documental (Sentinel) |
| --- | --- | --- |
| Campos variables por categoría | Tabla EAV (`ticket_id`, `clave`, `valor` texto) o muchas columnas NULL. | Subdocumento `campos_personalizados` con tipos nativos. |
| Alta de categoría nueva | Nuevas filas de metadatos y migraciones de esquema (`ALTER TABLE`). | Un documento nuevo en `categorias`; esquema dinámico en `tickets`. |
| Leer un ticket completo | Join entre 6 tablas (tickets, valores, comentarios, historial, adjuntos). | Un `findOne` sobre un único documento. |
| Evolución del modelo | Cada cambio exige coordinar esquema y código. | Versionado de esquema (`schema_version`) en los documentos. |

La justificación no es que MongoDB sea mejor en general, sino que **este dominio tiene la forma exacta para la que fue pensado**: agregados con partes anidadas, estructura variable por tipo y un esquema que evoluciona naturalmente con el servicio.

## 4. Requerimientos funcionales principales

| Id | Requerimiento | Prioridad |
| --- | --- | --- |
| RF-01 | Crear un ticket validando los campos personalizados contra su categoría. | Núcleo |
| RF-02 | Obtener un ticket por ID o número (`INC-2026-000142`) con todo su contexto. | Núcleo |
| RF-03 | Listar tickets con filtros (estado, prioridad, agente) y paginación. | Núcleo |
| RF-04 | Actualizar datos y cambiar estado respetando las transiciones permitidas. | Núcleo |
| RF-05 | Agregar comentarios actualizando contadores y SLA de primera respuesta atómicamente. | Núcleo |
| RF-06 | Asignar un ticket a un agente verificando capacidad máxima (Transaccionalidad). | Núcleo |
| RF-07 | Calcular límites de SLA al crear el ticket y registrar cumplimiento. | Núcleo |
| RF-08 | Administrar categorías (campos, transiciones, tiempos SLA). | Núcleo |

## 5. Casos de uso y alcance sobre colecciones

Se identifican casos de uso críticos para el modelado transaccional y atómico:
*   **CU-01 Crear ticket:** El solicitante elige la categoría y completa la plantilla. El sistema numera atómicamente (`contadores`), calcula el SLA y guarda (`tickets`).
*   **CU-02 Asignar/Reasignar (Transaccional):** El supervisor elige al agente. El sistema verifica capacidad y actualiza el `agente_id` en el ticket y la `carga_actual` en el agente simultáneamente (`tickets`, `agentes`).
*   **CU-03 Comentar:** El agente agrega una respuesta, añadiéndola al arreglo de comentarios y actualizando las métricas en un solo paso (`tickets`).

---

## 6. Entidades, Colecciones y Estructura de Documentos

El modelo cuenta con cinco colecciones para balancear flexibilidad y rendimiento.

### Colección `tickets` (Entidad Principal)
Almacena toda la información del incidente. Los campos opcionales pueden estar ausentes y las consultas lo contemplan.
*   **Obligatorios:** `numero`, `titulo`, `descripcion`, `categoria`, `estado`, `solicitante`, `sla`, `comentarios`, `historial`.
*   **Opcionales:** `agente` (hasta ser asignado), `etiquetas`, `adjuntos`, `satisfaccion`.

```json
{
  "_id": ObjectId("66f1a2b3c4d5e6f7a8b9c0d1"),
  "numero": "INC-2026-000142",
  "titulo": "La notebook no enciende tras un corte de luz",
  "descripcion": "Desde el lunes no da video ni enciende el LED de carga.",
  "categoria": { "codigo": "HW_FALLA", "nombre": "Falla de hardware" },
  "prioridad": "alta",
  "estado": "en_progreso",
  "solicitante": {
    "cliente_id": ObjectId("66f1a2b3c4d5e6f7a8b9b001"),
    "nombre": "Marta Quiroga",
    "email": "marta.quiroga@org.edu",
    "sede": "Sede Norte"
  },
  "agente": {
    "agente_id": ObjectId("66f1a2b3c4d5e6f7a8b9a003"),
    "nombre": "Diego Paz"
  },
  "campos_personalizados": {
    "equipo": { "inventario": "INV-004512", "tipo": "notebook", "marca": "Lenovo" },
    "sintoma": "no_enciende",
    "garantia_vigente": true
  },
  "sla": {
    "respuesta_limite": ISODate("2026-10-19T13:12:00Z"),
    "resolucion_limite": ISODate("2026-10-19T20:12:00Z"),
    "incumplido": false
  },
  "comentarios": [
    {
      "autor": { "tipo": "agente", "nombre": "Diego Paz" },
      "texto": "Voy a retirar el equipo para probar la fuente.",
      "fecha": ISODate("2026-10-19T12:40:00Z")
    }
  ],
  "historial": [
    { "fecha": ISODate("2026-10-19T12:12:00Z"), "tipo": "estado", "de": null, "a": "nuevo" }
  ],
  "metricas": { "cant_comentarios": 1, "reaperturas": 0 },
  "schema_version": 1
}
```

### Colección `categorias` (Plantillas de Servicio)
Define qué datos pide cada tipo de ticket, qué plazos se prometen y qué transiciones son válidas.
```json
{
  "_id": "HW_FALLA",
  "nombre": "Falla de hardware",
  "activa": true,
  "campos_personalizados": [
    { "clave": "equipo.inventario", "tipo": "string", "obligatorio": true },
    { "clave": "sintoma", "tipo": "enum", "opciones": ["no_enciende", "lento", "ruido"] }
  ],
  "sla": {
    "alta": { "respuesta_min": 60, "resolucion_min": 480 }
  },
  "transiciones": {
    "nuevo": ["asignado", "cancelado"],
    "asignado": ["en_progreso", "cancelado"]
  }
}
```

### Otras Colecciones Auxiliares
*   **`agentes`:** Personal de soporte. Guarda `carga_actual` como valor transaccional.
```json
  {
  "_id": ObjectId("66f1a2b3c4d5e6f7a8b9a003"),
  "nombre": "Diego Paz",
  "email": "diego.paz@org.edu",
  "rol": "tecnico",
  "nivel": 2,
  "habilidades": ["hardware", "impresoras"],
  "sede_base": "Sede Norte",
  "turno": { dias: [1, 2, 3, 4, 5], desde: "08:00", hasta: "16:00" },
  'capacidad_maxima": 8,
  "carga_actual": 5,
  "activo": true
  }
```
*   **`clientes`:** Solicitantes. Embebe sus `equipos` (1 a 5 por persona) para rápida lectura.
```json
{
  "_id": ObjectId("66f1a2b3c4d5e6f7a8b9b001"),
  "nombre": "Marta Quiroga",
  "email": "marta.quiroga@org.edu",
  "tipo": "docente",
  "area": "Departamento de Matemática",
  "sede": "Sede Norte",
  "prioritario": false,
  "equipos": [
    { inventario: "INV-004512", tipo: "notebook", marca: "Lenovo", modelo: "T14", garantia_hasta: ISODate("2027-03-31T00:00:00Z") }
  ],
  "creado": ISODate("2025-02-10T11:00:00Z")
```
*   **`contadores`:** Resuelve la numeración correlativa (`INC-2026-XXX`) mediante un documento simple `{ _id: "ticket-2026", valor: 142 }`.
```json
{ "_id": "ticket-2026", valor: 142 }

```

---

## 7. Relaciones y decisiones de modelado: embeber vs referenciar

El diseño de Sentinel prioriza la lectura rápida y completa del ticket, justificando las siguientes decisiones arquitectónicas:

*   **Embebido (Documentos Anidados y Arreglos):** Se anidan los `comentarios`, el `historial` de estados, los metadatos de `adjuntos` y los límites de `sla` dentro de la colección `tickets`. Esta decisión se fundamenta en que un ticket es un "agregado" lógico: la interfaz requiere todo su contexto histórico en una sola vista, resolviéndose con un único `findOne` a disco sin unir tablas adicionales. Adicionalmente, en `clientes`, se embeben los `equipos` asignados dado que son pocos y se leen conjuntamente al buscar al solicitante.
*   **Referenciado Estándar:** Se utiliza una referencia por código natural (`_id: "HW_FALLA"`) desde `tickets` hacia `categorias`. Esto permite que la definición del servicio y los SLA evolucionen independientemente sin tener que reescribir masivamente los tickets históricos.

## 8. Patrones de diseño documental aplicados

Para mitigar las limitaciones de las referencias y optimizar el rendimiento, se implementan:
*   **Patrón de Referencia Extendida (Extended Reference):** Al relacionar un ticket con su `agente` y `solicitante`, no solo se guarda el `ObjectId`, sino que se embebe una copia de los datos de lectura frecuente (nombre, email). Esto elimina los `$lookup` al listar bandejas de entrada.
*   **Patrón de Valor Calculado (Computed Pattern):** La `carga_actual` en agentes y las `metricas` (cantidad de comentarios) en tickets se actualizan en el momento de la escritura para evitar realizar un `$count` sobre miles de documentos en cada lectura del tablero.
*   **Patrón de Atributos Polimórficos:** El subdocumento `campos_personalizados` permite que la estructura varíe dinámicamente.
*   **Versionado de Esquema (Schema Versioning):** El campo `schema_version` prepara a la base para convivir con alteraciones estructurales futuras sin inhabilitar el código existente.

## 9. Patrones de acceso: consultas e índices previstos

El sistema responderá a las necesidades operativas de la mesa de ayuda mediante consultas optimizadas:
*   **Bandeja del agente:** Filtro por `agente.agente_id` y `estado` ("en_progreso"), ordenado por `sla.resolucion_limite` ascendente. Requerirá un **índice compuesto** para evitar un escaneo completo de la colección.
*   **Búsqueda dinámica:** Dado que los `campos_personalizados` varían, se prevé la creación de un **índice Wildcard** (`campos_personalizados.$**`) para permitir búsquedas eficientes por valores específicos (ej. una "VLAN") sin conocer la ruta exacta.

## 10. Consistencia y transacciones

El mantenimiento de la integridad referencial se divide en dos enfoques:
*   **Operaciones Atómicas en un Documento:** La numeración correlativa (`INC-2026-000142`) usa `findOneAndUpdate` con `$inc` sobre `contadores`. Agregar un comentario usa `$push` (para el texto) e `$inc` (para `cant_comentarios`) de forma simultánea.
*   **Transacción Multidocumento:** Esencial para la *Asignación de Tickets*. Si un supervisor asigna un incidente, el sistema actualiza el `agente_id` en el ticket e incrementa la `carga_actual` en el agente simultáneamente. Una falla a la mitad corrompería la capacidad operativa. Se utilizará una sesión transaccional (requiriendo un Replica Set).

## 11. Análisis de datos previsto

A partir de los datos almacenados (250-300 tickets de prueba), se desarrollará un módulo analítico en Python (Pandas/Matplotlib). Los datos se generarán intencionalmente con patrones (ej. picos de lunes, un área con SLA deficitario).
Se calcularán métricas clave como:
1.  Cumplimiento de SLA por categoría.
2.  Tiempo medio de resolución (TMR).
3.  Carga de trabajo real vs. capacidad máxima de agentes.
El objetivo del análisis será derivar en decisiones accionables, como la redistribución de personal hacia el área más afectada.


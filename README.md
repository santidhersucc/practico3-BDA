# Sentinel · Plataforma de gestión de incidentes sobre MongoDB

Gestión de tickets de soporte para una organización con varias sedes: base documental en MongoDB, API REST con capa de
repositorios, caso de consistencia con transacciones y tests automatizados.

## Estado del proyecto

| Entrega | Contenido | Estado |
|---|---|---|
| 1 · Diseño | Requerimientos, modelo documental, justificación → `Entrega_parcial_1.md` | ✔ |
| 2 · Base y consultas | Carga reproducible, 12 consultas, índices, explain, prueba de consistencia en mongosh → `Entrega_parcial_2.md` | ✔ |
| 3 · API y consistencia | API FastAPI con CRUD, repositorios, validaciones, manejo de errores, transacciones y 53 tests (secciones 8 a 10) → `Entrega_parcial_3.md` | ✔ |
| 4 · Integración | Docker Compose, notebook de análisis, documentación final y defensa | pendiente |

## Qué hay en esta carpeta

```
data/                         5 archivos NDJSON ya generados (categorias, agentes, clientes, tickets, contadores)
requirements.txt              pymongo (solo para cargar_datos.py)
scripts/generar_datos.py      regenera data/ (opcional: los datos ya vienen incluidos)
scripts/verificar_datos.py    chequea los archivos de data/ sin necesitar MongoDB
scripts/cargar_datos.py       crea las colecciones (con validadores), carga los datos y verifica la carga
consultas/indices.js          crea los índices
consultas/consultas.js        12 consultas comentadas
consultas/explain.js          explain("executionStats") con y sin índice
consultas/consistencia.js     prueba de la transacción de asignación (mongosh)
api/                          API REST (FastAPI + PyMongo)
  requirements.txt            dependencias de la API y de los tests
  pytest.ini                  configuración de pytest
  app/
    main.py                   crea la app FastAPI (+ GET /health)
    config.py                 lee las variables de entorno
    db.py                     MongoClient único, get_db() y en_transaccion()
    errors.py                 errores del dominio → respuestas HTTP
    schemas/ticket.py         modelos Pydantic de entrada y salida
    routers/tickets.py        endpoints HTTP
    services/tickets_service.py   reglas de negocio: SLA, transiciones, campos personalizados, asignación
    repositories/             ÚNICO acceso a MongoDB, un módulo por colección
      tickets_repo.py         buscar, listar, insertar, actualizar, cambiar estado, asignar, reasignar, comentar, eliminar
      categorias_repo.py      buscar por código (campos, SLA y transiciones)
      agentes_repo.py         buscar, +1 carga solo si hay cupo, -1 carga
      clientes_repo.py        buscar solicitante (para la referencia extendida)
      contadores_repo.py      siguiente número de ticket ($inc atómico)
  tests/
    conftest.py               crea, limpia y borra la base de prueba sentinel_test
    test_crud.py              38 tests de endpoints, validaciones y errores
    test_consistencia.py      15 tests del caso de consistencia y concurrencia
docs/capturas/                capturas de Swagger usadas en Entrega_parcial_3.md
.gitignore                    archivos que no se suben: __pycache__, .pytest_cache, .env, entornos virtuales, .claude/
```

## Resumen rápido (si ya tenés Docker y Python)

```bash
docker run -d --name sentinel-mongo -p 27017:27017 mongo:7 --replSet rs0
docker exec sentinel-mongo mongosh --quiet --eval "rs.initiate({_id:'rs0', members:[{_id:0, host:'localhost:27017'}]})"
pip install -r requirements.txt -r api/requirements.txt
python scripts/cargar_datos.py
docker exec -i sentinel-mongo mongosh sentinel < consultas/indices.js
python -m uvicorn app.main:app --app-dir api --reload      # API en http://localhost:8000/docs
python -m pytest api/tests -v                              # tests (no tocan la base sentinel)
```

El detalle de cada paso está abajo. **En Windows**: si `python` no funciona, usá `py -3` (ver paso 4), y en PowerShell
el `<` no funciona: usá `Get-Content consultas/indices.js | docker exec -i sentinel-mongo mongosh sentinel` (ver paso 5).

---

## 1. Qué necesitás instalar

| Herramienta | Para qué | ¿Obligatoria? |
|---|---|---|
| **Docker Desktop** | Corre el servidor de MongoDB en un contenedor (ya trae `mongosh` adentro y Docker Compose) | Sí (recomendado) |
| **Python 3.10+** | Cargar los datos, correr la API y los tests | Sí |
| **MongoDB Compass** | Ver los datos con interfaz gráfica | No |
| **mongosh** en tu PC | Correr los `.js` directamente | No (se puede usar el del contenedor) |

> **MongoDB Compass no es el servidor**: es solo un cliente para mirar la base. Sin un servidor corriendo (el contenedor)
> Compass no tiene a qué conectarse.

### ¿Por qué replica set?

Las **transacciones multidocumento** (asignar un ticket y subir la carga del agente a la vez, o resolver/cancelar y
bajarla) solo funcionan en un replica set; una instancia *standalone* no las soporta. Usamos un replica set de **un solo
miembro**: no aporta copias, pero habilita las transacciones. Lo necesitan `consistencia.js`, la API y los tests.

## 2. Instalar Docker Desktop (una sola vez)

1. Descargarlo de docker.com → *Docker Desktop for Windows* (en Mac/Linux, la versión correspondiente).
   **No** hace falta instalar Docker Compose aparte: viene incluido.
2. Ejecutar el instalador y dejar tildada la opción **WSL 2**. Reiniciar si lo pide.
3. Abrir Docker Desktop, aceptar los términos (la cuenta es opcional: *Skip*) y esperar a que diga **Engine running**.
4. Comprobar en una terminal:
   ```bash
   docker --version
   docker compose version
   ```

**Si el instalador falla con "Virtual Machine Platform is not enabled"** (Windows): abrir PowerShell **como
administrador**, ejecutar `wsl --install` (tarda varios minutos sin mostrar nada; es normal), reiniciar la PC y volver a
correr el instalador. Otra opción es ejecutar el instalador como administrador y elegir *All-users installation*.
Si después Docker dice que la virtualización está deshabilitada, hay que activarla en la BIOS (se puede ver en
Administrador de tareas → Rendimiento → CPU → *Virtualización*).

## 3. Crear el contenedor de MongoDB (una sola vez)

```bash
docker run -d --name sentinel-mongo -p 27017:27017 mongo:7 --replSet rs0
```

- La primera vez descarga la imagen `mongo:7` (~250 MB). Después arranca en segundos.
- `-p 27017:27017` expone MongoDB en `localhost:27017` de tu PC.
- `--replSet rs0` lo arranca como parte del replica set `rs0`.

Activar el replica set (una sola vez):

```bash
docker exec sentinel-mongo mongosh --quiet --eval "rs.initiate({_id:'rs0', members:[{_id:0, host:'localhost:27017'}]})"
```

Tiene que responder `{ ok: 1 }`. Se declara el miembro como `localhost:27017` porque si no, MongoDB se anuncia con el
nombre interno del contenedor (algo como `24eb1b8cbb1c:27017`), que no existe fuera de Docker.

Verificar:

```bash
docker exec sentinel-mongo mongosh --quiet --eval "rs.status().members.map(m => m.name + ' ' + m.stateStr)"
```

Debe mostrar `localhost:27017 PRIMARY`.

### Uso diario del contenedor

| Situación | Comando |
|---|---|
| Después de reiniciar la PC (abrir Docker Desktop primero) | `docker start sentinel-mongo` |
| Apagarlo | `docker stop sentinel-mongo` |
| Ver si está corriendo | `docker ps` |
| Borrarlo por completo (**se pierden los datos**) | `docker rm -f sentinel-mongo` |

`docker run` **crea** el contenedor (se usa una vez; si lo repetís falla porque el nombre ya existe).
`docker start` lo vuelve a prender. `docker exec` ejecuta un programa **dentro** de un contenedor que ya está corriendo.

## 4. Preparar Python

```bash
pip install -r requirements.txt -r api/requirements.txt
```

- `requirements.txt` (raíz): solo `pymongo`, para `cargar_datos.py`.
- `api/requirements.txt`: `fastapi`, `uvicorn`, `pymongo`, `pydantic`, `pytest` y `httpx`, para la API y los tests.

> **Windows**: si `python` abre la Microsoft Store o dice "no se encontró Python", es porque Python no está en el PATH y
> el alias de la Store intercepta el comando. Usá el lanzador **`py -3`** en su lugar: `py -3 -m pip install ...`,
> `py -3 scripts/cargar_datos.py`, `py -m uvicorn ...`, `py -m pytest ...`. El `-3` importa con los scripts: tienen la
> línea `#!/usr/bin/env python3` y `py` sin versión la obedece e intenta abrir `python3`, que vuelve a caer en el alias de
> la Store. Otra opción: reinstalar Python tildando *Add python.exe to PATH* y desactivar el alias en Configuración →
> Aplicaciones → Configuración avanzada de aplicaciones → Alias de ejecución de aplicaciones. En Mac/Linux suele ser `python3`.
>
> Si al instalar aparece *"The script ... is installed in '...\Scripts' which is not on PATH"*, `uvicorn` y `pytest` no
> se encuentran como comando: correlos siempre con `py -m` adelante.

## 5. Cargar los datos y crear los índices

```bash
# Borra y recrea las colecciones de la base "sentinel" (con validadores), carga data/*.json y verifica
python scripts/cargar_datos.py
```

Si MongoDB no está en `localhost:27017` (por ejemplo Atlas), antes definí `MONGO_URI`:
`export MONGO_URI="mongodb://..."` (bash) o `$env:MONGO_URI="mongodb://..."` (PowerShell).

Después, crear los índices. Hay tres formas equivalentes según lo que tengas:

```bash
# a) Con mongosh instalado en tu PC
mongosh sentinel --file consultas/indices.js

# b) Sin mongosh, usando el del contenedor — bash / Git Bash / Mac / Linux
docker exec -i sentinel-mongo mongosh sentinel < consultas/indices.js

# c) Sin mongosh, usando el del contenedor — Windows PowerShell
Get-Content consultas/indices.js | docker exec -i sentinel-mongo mongosh sentinel
```

> `cargar_datos.py` borra las colecciones **y sus índices**: cada vez que lo vuelvas a correr, repetí los índices.

Verificar que quedó todo (cantidad de documentos e índices por colección):

```bash
docker exec sentinel-mongo mongosh sentinel --quiet --eval "db.getCollectionNames().sort().forEach(c => print(c, db[c].countDocuments(), db[c].getIndexes().map(i => i.name).join(',')))"
```

Resultado esperado: `agentes 10`, `categorias 5`, `clientes 60`, `contadores 1`, `tickets 280`, con los índices
`idx_bandeja_agente`, `uq_ticket_numero`, `idx_wildcard_campos`, `idx_categoria_creado`, `uq_agente_email` y `uq_cliente_email`.

## 6. Consultas, explain y consistencia (mongosh)

Mismo patrón que los índices: con `mongosh` local, o con el del contenedor.

| Script | Con mongosh local | Sin mongosh (PowerShell) | Sin mongosh (bash) |
|---|---|---|---|
| Consultas | `mongosh sentinel --file consultas/consultas.js` | `Get-Content consultas/consultas.js \| docker exec -i sentinel-mongo mongosh sentinel` | `docker exec -i sentinel-mongo mongosh sentinel < consultas/consultas.js` |
| Explain | `mongosh sentinel --file consultas/explain.js` | `Get-Content consultas/explain.js \| docker exec -i sentinel-mongo mongosh sentinel` | `docker exec -i sentinel-mongo mongosh sentinel < consultas/explain.js` |
| Consistencia (requiere replica set) | `mongosh sentinel --file consultas/consistencia.js` | `Get-Content consultas/consistencia.js \| docker exec -i sentinel-mongo mongosh sentinel` | `docker exec -i sentinel-mongo mongosh sentinel < consultas/consistencia.js` |

- `consultas.js` y `explain.js` solo leen.
- `consistencia.js` crea tickets de prueba (`INC-9999-*`), modifica la carga de un agente y al final deja los datos como estaban.

Si usás Atlas o un servidor remoto con mongosh local, reemplazá `sentinel` por la cadena completa:
`mongosh "mongodb+srv://.../sentinel" --file ...`

Para repetir todo desde cero alcanza con volver a correr el paso 5 (datos + índices).

## 7. Conectarse con MongoDB Compass

Nueva conexión con la URI:

```
mongodb://localhost:27017/?directConnection=true
```

Se ve la base `sentinel` con sus 5 colecciones (las bases `admin`, `config` y `local` son internas de MongoDB).

---

## 8. Levantar la API

Con el contenedor corriendo y los datos cargados (pasos 3 a 5), desde la raíz del repo:

```bash
py -m uvicorn app.main:app --app-dir api --reload
```

(o, parado dentro de `api/`: `py -m uvicorn app.main:app --reload`). Queda en `http://localhost:8000`:

- **Swagger** (probar los endpoints desde el navegador): `http://localhost:8000/docs` → abrir un endpoint →
  *Try it out* → completar → *Execute*.
- **Health check**: `http://localhost:8000/health` → `{"status": "ok", "base": "sentinel"}` (503 si MongoDB no responde).
- `--reload` reinicia la API sola cada vez que se guarda un archivo. `Ctrl+C` la detiene.

> Lo que hagas desde Swagger **modifica la base `sentinel`**. Para volver a los datos originales: paso 5
> (`py -3 scripts/cargar_datos.py` + índices).

### Endpoints

| Método | Ruta | Qué hace | Respuestas |
|---|---|---|---|
| POST | `/tickets` | Crear ticket | 201, 422 |
| GET | `/tickets?estado=&prioridad=&agente_id=&page=&size=` | Listar con filtros y paginación (`size` máx. 100) | 200, 422 |
| GET | `/tickets/{numero}` | Obtener un ticket (`INC-2026-000001`) | 200, 404, 422 |
| PATCH | `/tickets/{numero}` | Editar título, descripción, prioridad o etiquetas | 200, 404, 409, 422 |
| PATCH | `/tickets/{numero}/estado` | Cambiar estado | 200, 404, 409, 422 |
| POST | `/tickets/{numero}/comentarios` | Agregar comentario | 201, 404, 409, 422 |
| POST | `/tickets/{numero}/asignar` | Asignar / reasignar agente (transacción) | 200, 404, 409, 422 |
| DELETE | `/tickets/{numero}` | Eliminar (solo `nuevo` o `cancelado`) | 204, 404, 409 |
| GET | `/health` | Verifica la conexión a MongoDB | 200, 503 |

El identificador en las rutas es el **número de ticket** (`INC-2026-000001`): es único (índice `uq_ticket_numero`) y es
el que usa el negocio, en lugar del `_id` interno de MongoDB.

Ejemplo de body para crear (categoría `SW_ACCESO`):

```json
{
  "titulo": "Sin acceso al SIU",
  "descripcion": "No puedo entrar con mi usuario",
  "categoria": "SW_ACCESO",
  "prioridad": "media",
  "solicitante_id": "66f1a2b3c4d5e6f7a800b001",
  "campos_personalizados": { "aplicacion": "SIU", "tipo_acceso": "reset_clave" }
}
```

Para asignar, un `agente_id` válido es `66f1a2b3c4d5e6f7a800a002` (Lucía Ferreyra).

### Configuración (variables de entorno)

| Variable | Default | Para qué |
|---|---|---|
| `MONGO_URI` | `mongodb://localhost:27017/?directConnection=true` | Dónde está MongoDB (la misma que usa `cargar_datos.py`) |
| `MONGO_DB` | `sentinel` | Base a usar (los tests usan `sentinel_test`) |
| `ANIO_NUMERACION` | `2026` | Año de la numeración `INC-AAAA-NNNNNN` (contador `ticket-<año>`) |

## 9. Correr los tests

Requisitos: el contenedor corriendo como replica set (paso 3) y las dependencias de `api/requirements.txt`.
**No hace falta cargar datos ni levantar la API.** Desde la raíz del repo:

```bash
py -m pytest api/tests -v
```

Resultado esperado: `53 passed`. Para correr un solo archivo: `py -m pytest api/tests/test_consistencia.py -v`.

**Los tests no tocan la base `sentinel`.** Usan una base descartable `sentinel_test` dentro del mismo contenedor:

1. Al empezar, `conftest.py` crea `sentinel_test` desde `data/*.json`, con los mismos validadores que
   `cargar_datos.py` y los mismos índices que `indices.js`.
2. Antes de **cada** test la vacía y la vuelve a poblar: todos arrancan desde los mismos datos.
3. Al terminar la borra.

Si MongoDB no responde o no es replica set, pytest se detiene con un mensaje que lo indica.

| Archivo | Qué prueba |
|---|---|
| `test_crud.py` | Crear (numeración, SLA, referencia extendida, campos personalizados inválidos, referencias inexistentes, formato); obtener (404, formato); listar (filtros, paginación, parámetros inválidos); editar (recálculo de SLA, tickets cerrados); comentar (primera respuesta); transiciones permitidas y no permitidas; eliminar (permitido / 409 / 404) |
| `test_consistencia.py` | Escenarios de `consistencia.js` contra la API — **A** asignación correcta, **B** falla entre las dos escrituras → rollback, **C** agente sin cupo, **D** demostración de la inconsistencia sin transacción —; agente inactivo/inexistente; reasignación (mueve la carga / sin cupo no cambia nada); ciclo de vida resolver–reabrir–cancelar; **concurrencia**: 10 asignaciones simultáneas por el último cupo (entra 1) y 5 pedidos simultáneos para el mismo ticket (se asigna 1 vez). Cada test verifica al final que `carga_actual` de todos los agentes coincida con sus tickets abiertos |

## 10. Cómo está hecha la API

### Capas

**router** (solo HTTP) → **service** (reglas de negocio) → **repository** (consultas a MongoDB).

- `routers/tickets.py` lee parámetros, llama al servicio y elige el código de respuesta. Los endpoints son `def` (no
  `async def`) porque PyMongo es bloqueante: FastAPI los corre en un thread pool.
- `services/tickets_service.py` aplica las reglas y lanza errores del dominio; no sabe nada de HTTP ni ejecuta consultas.
- `repositories/` son los únicos que ejecutan `find`, `insert_one`, `update_one`, etc.

### Errores

Los servicios lanzan errores del dominio y `errors.py` los traduce. Formato de todos los errores:
`{"error": "<codigo>", "detalle": "<mensaje>"}`.

| Error | HTTP | Ejemplo |
|---|---|---|
| `NoEncontrado` | 404 | el ticket no existe |
| `Conflicto` | 409 | transición de estado no permitida, agente sin cupo, borrar un ticket abierto |
| `Validacion` | 422 | campos personalizados que no cumplen la definición de la categoría |
| clave duplicada (índice único) | 409 | número de ticket o email repetido |
| MongoDB no responde | 503 | el contenedor está apagado (`docker start sentinel-mongo`) |

### Validación en dos niveles

1. **Formato** (Pydantic, `schemas/ticket.py`): tipos, campos obligatorios, prioridad/estado dentro de los valores
   permitidos, ids con formato de ObjectId, y **campos desconocidos rechazados**. FastAPI responde 422 automáticamente.
2. **Reglas de negocio** (servicio): lo que depende de la base — que la categoría exista y los `campos_personalizados`
   cumplan su definición, que la transición de estado esté permitida, que el agente tenga cupo.

| Modelo | Se usa en |
|---|---|
| `TicketCrear` | `POST /tickets` — titulo, descripcion, categoria (código), prioridad, solicitante_id, campos_personalizados, etiquetas, adjuntos |
| `TicketActualizar` | `PATCH /tickets/{numero}` — titulo, descripcion, prioridad, etiquetas (al menos uno) |
| `CambioEstado` | `PATCH /tickets/{numero}/estado` — estado y motivo opcional |
| `ComentarioCrear` | `POST /tickets/{numero}/comentarios` — autor {tipo, nombre} y texto |
| `Asignacion` | `POST /tickets/{numero}/asignar` — agente_id |
| `TicketRespuesta` / `TicketResumen` / `PaginaTickets` | respuestas: ticket completo, versión liviana para listados, página con total |

El estado, el número, el SLA, las métricas y el historial **no** se reciben en el request: los calcula la API.

### Reglas de negocio

| Operación | Reglas | Errores |
|---|---|---|
| Crear (CU-01) | categoría existente y activa; `campos_personalizados` validados contra la categoría (obligatorios, tipo `string`/`int`/`double`/`bool`, opciones de `enum`; se permiten claves extra); solicitante existente; número con `contadores`; SLA = ahora + minutos de la categoría según prioridad; estado `nuevo` | 422 |
| Editar | no en `cerrado`/`cancelado`; cambiar la prioridad recalcula los límites de SLA y deja un evento `prioridad` en el historial | 404, 409 |
| Cambiar estado | solo transiciones permitidas por la categoría; a `asignado` solo por `/asignar`; al resolver guarda `resuelto_en` y si se incumplió el SLA; reabrir (`resuelto → en_progreso`) suma una reapertura | 404, 409 |
| Comentar (CU-03) | no en `cerrado`/`cancelado`; el primer comentario de un agente registra `sla.primera_respuesta_en` | 404, 409 |
| Asignar / reasignar (CU-02) | agente existente y activo; ticket en `nuevo` (asigna) o abierto (reasigna, distinto agente) | 404, 409, 422 |
| Eliminar (RF-09) | solo en `nuevo` o `cancelado` (lo demás se cancela, no se borra) | 404, 409 |

### Consistencia: ticket + carga del agente

`carga_actual` del agente = cantidad de tickets suyos en `asignado`, `en_progreso` o `en_espera`. Asignar un ticket
toca **dos documentos en dos colecciones**: si se actualizara el ticket y fallara el `$inc` del agente, la carga quedaría
desfasada (es lo que demuestra el test D).

- Todo cambio que hace entrar o salir un ticket de ese grupo ajusta la carga **en la misma transacción**
  (`session.with_transaction`): asignar (+1), reasignar (+1 nuevo / −1 anterior), resolver o cancelar (−1, CU-04) y
  reabrir (+1, con control de cupo). Si cualquier paso falla se lanza `Conflicto`, la transacción se aborta y no queda
  nada a medias (test B).
- Los cambios que no tocan la carga (p. ej. `asignado → en_progreso`) usan un solo update atómico, sin transacción.
- El **control de cupo** va dentro del filtro del update
  (`$expr: {$lt: ["$carga_actual", "$capacidad_maxima"]}` + `$inc: 1`), no en un `if` previo en Python: MongoDB evalúa
  la condición y aplica el incremento de forma atómica, así dos asignaciones simultáneas no pueden superar la capacidad
  (test de concurrencia: 10 intentos por 1 cupo, entra solo 1).

### Operaciones atómicas sin transacción

- **Comentar**: `$push` del comentario + `$inc` de `metricas.cant_comentarios` + `$set` de fechas en el mismo update
  sobre un solo documento.
- **Numeración** `INC-AAAA-NNNNNN`: `find_one_and_update` + `$inc` sobre `contadores` (50 pedidos en paralelo recibieron
  50 números distintos). Si no existe el contador del año, se crea (`upsert`) y arranca en 1.

### Repositorios

Un módulo por colección. Dos ideas que se repiten:

- **`session=None`** en todas las funciones: sueltas funcionan solas; dentro de `en_transaccion()` el servicio les pasa
  la sesión y quedan en la misma transacción.
- **Estado esperado en el filtro** (`{"numero": ..., "estado": "nuevo"}`): si otro request cambió el ticket entre la
  lectura y la escritura, no matchea y la función devuelve `None`/`False` → el servicio responde 409. Así no se pisa
  un cambio concurrente.

---

## Qué guardar como evidencia

- **Entrega 2**: la salida de consola de los pasos 5 y 6; se pega en `Entrega_parcial_2.md`, que tiene los lugares
  marcados con **COMPLETAR**. Los resultados de `explain.js` en particular **no están escritos de antemano**: son los que
  salgan en tu máquina.
- **Entrega 3**: la salida de `py -m pytest api/tests -v` (sección 9) y las capturas de Swagger (sección 8, guardadas en
  `docs/capturas/`) ya están en `Entrega_parcial_3.md`.

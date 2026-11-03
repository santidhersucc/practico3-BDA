# Sentinel · Plataforma de gestión de incidentes sobre MongoDB

Gestión de tickets de soporte para una organización con varias sedes: base documental en MongoDB, API REST con capa de
repositorios, caso de consistencia con transacciones y tests automatizados.

## Estado del proyecto

| Entrega | Contenido | Estado |
|---|---|---|
| 1 · Diseño | Requerimientos, modelo documental, justificación → `Entrega_parcial_1.md` | ✔ |
| 2 · Base y consultas | Carga reproducible, 12 consultas, índices, explain, prueba de consistencia en mongosh → `Entrega_parcial_2.md` | ✔ |
| 3 · API y consistencia | API FastAPI con CRUD, repositorios, validaciones, manejo de errores, transacciones y 53 tests (secciones 8 a 10) → `Entrega_parcial_3.md` | ✔ |
| 4 · Integración | Docker Compose (MongoDB + API) ✔ · notebook de análisis, informe final y defensa: pendiente | en curso |

## Qué hay en esta carpeta

```
docker-compose.yml            servicios mongo (replica set + volumen) y api
Dockerfile                    imagen de la API (también ejecuta los scripts de carga y los tests)
.env.example                  variables de configuración de ejemplo (sin credenciales)
.dockerignore                 archivos que no entran a la imagen
data/                         5 archivos NDJSON ya generados (categorias, agentes, clientes, tickets, contadores)
requirements.txt              pymongo (solo si cargás los datos desde tu PC, sin contenedor)
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

## Resumen rápido (si ya tenés Docker)

```bash
docker compose up -d --build                                                      # MongoDB (replica set) + API
docker compose exec api python scripts/cargar_datos.py                            # datos de prueba
docker compose exec mongo mongosh sentinel --quiet --file /consultas/indices.js   # índices
docker compose exec api python -m pytest api/tests -v                             # 53 tests (no tocan la base sentinel)
# Swagger: http://localhost:8000/docs        Detener: docker compose down
```

No hace falta Python en tu PC: la carga de datos, la API y los tests corren dentro de los contenedores. El detalle de
cada paso está abajo.

---

## 1. Qué necesitás instalar

| Herramienta | Para qué | ¿Obligatoria? |
|---|---|---|
| **Docker Desktop** | Corre MongoDB y la API en contenedores (ya trae Docker Compose) | Sí |
| **Git** | Clonar el repositorio (o descargar el zip desde GitHub) | Sí |
| **MongoDB Compass** | Ver los datos con interfaz gráfica | No |
| **Python 3.10+** y **mongosh** en tu PC | Solo para ejecutar scripts, API o tests fuera de los contenedores (sección 4) | No |

> **Puerto 27017:** si ya tenés otro MongoDB usándolo (por ejemplo, instalado como servicio de Windows), detenelo
> (`Stop-Service MongoDB` en PowerShell como administrador) o cambiá `MONGO_PORT` en `.env` (sección 3).
>
> **MongoDB Compass no es el servidor**: es solo un cliente para mirar la base. Sin el contenedor `mongo` corriendo,
> Compass no tiene a qué conectarse.

### ¿Por qué replica set?

Las **transacciones multidocumento** (asignar un ticket y subir la carga del agente a la vez, o resolver/cancelar y
bajarla) solo funcionan en un replica set; una instancia *standalone* no las soporta. Usamos un replica set de **un solo
miembro**: no aporta copias, pero habilita las transacciones. Lo necesitan `consistencia.js`, la API y los tests.
Docker Compose lo inicializa solo (sección 3): no hay que ejecutar `rs.initiate` a mano.

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

## 3. Iniciar y detener el entorno (Docker Compose)

Desde la raíz del repo (donde está `docker-compose.yml`):

```bash
docker compose up -d --build
docker compose ps
```

- `up -d --build` construye la imagen de la API (la primera vez tarda) y levanta los servicios en segundo plano.
- `ps` tiene que mostrar `sentinel-mongo` **(healthy)** y `sentinel-api` en ejecución. MongoDB tarda unos 15 segundos en
  quedar *healthy* porque se inicializa el replica set; la API espera a que lo esté.

| Servicio | Contenedor | Qué es | Puerto en tu PC |
|---|---|---|---|
| `mongo` | `sentinel-mongo` | MongoDB 7 como replica set `rs0` de un miembro. Los datos viven en el volumen `sentinel_mongo_data` | `127.0.0.1:27017` |
| `api` | `sentinel-api` | API FastAPI. Dentro de Compose se conecta con `mongodb://mongo:27017/?replicaSet=rs0` (nombre del servicio, no `localhost`) | `127.0.0.1:8000` |

El replica set lo inicializa el *healthcheck* del servicio `mongo` la primera vez y declara su miembro como `mongo:27017`.
Dentro de Compose la API usa ese nombre; desde tu PC (Compass, scripts o `mongosh` fuera del contenedor) hay que conectarse con
`directConnection=true` (sección 7).

### Variables de configuración

`.env.example` lista las variables; todas tienen valor por defecto, así que copiarlo a `.env` es opcional
(`cp .env.example .env`). **No contiene credenciales**: el MongoDB local no usa autenticación y `.env` está en `.gitignore`.

| Variable | Default | Para qué |
|---|---|---|
| `MONGO_PORT` | `27017` | Puerto de tu PC donde se publica MongoDB |
| `API_PORT` | `8000` | Puerto de tu PC donde se publica la API |
| `MONGO_DB` | `sentinel` | Base que usa la API |
| `ANIO_NUMERACION` | `2026` | Año de la numeración `INC-AAAA-NNNNNN` |

### Uso diario

| Situación | Comando |
|---|---|
| Levantar el entorno (los datos se conservan) | `docker compose up -d` |
| Detenerlo (los datos se conservan en el volumen) | `docker compose down` |
| Ver el estado | `docker compose ps` |
| Ver los logs | `docker compose logs -f api` (o `mongo`) |
| Cambié el código de la API | `docker compose up -d --build` |
| Borrar todo, **incluidos los datos** | `docker compose down -v` |
| Empezar desde cero | `docker compose down -v`, `docker compose up -d --build` y volver a cargar datos e índices (sección 5) |

Los datos persisten entre `down` y `up` gracias al volumen, así que alcanza con cargarlos una vez.
`docker compose up` crea el contenedor si no existe y lo enciende si está apagado; no hace falta `docker run`.

## 4. (Opcional) Ejecutar con Python en tu PC, sin contenedor `api`

Solo si querés correr los scripts, la API o los tests directamente en tu máquina. Requiere Python 3.10+ y el contenedor
`mongo` levantado (sección 3).

```bash
pip install -r requirements.txt -r api/requirements.txt
```

- `requirements.txt` (raíz): solo `pymongo`, para `cargar_datos.py`.
- `api/requirements.txt`: `fastapi`, `uvicorn`, `pymongo`, `pydantic`, `pytest` y `httpx`, para la API y los tests.

Desde tu PC los comandos son los mismos que en el contenedor, sin el prefijo `docker compose exec api`:
`python scripts/cargar_datos.py`, `python -m pytest api/tests -v`, y para la API con recarga automática primero
`docker compose stop api` (para liberar el puerto 8000) y luego `python -m uvicorn app.main:app --app-dir api --reload`.

> **Windows**: si `python` abre la Microsoft Store o dice "no se encontró Python", usá el lanzador **`py -3`**
> (`py -3 -m pip install ...`, `py -3 scripts/cargar_datos.py`, `py -m uvicorn ...`, `py -m pytest ...`). Si pip avisa que
> `...\Scripts` no está en el PATH, corré siempre `uvicorn` y `pytest` con `py -m` adelante.

## 5. Cargar los datos y crear los índices

```bash
# Borra y recrea las colecciones de la base "sentinel" (con validadores), carga data/*.json y verifica
docker compose exec api python scripts/cargar_datos.py

# Crea los índices (con el mongosh del contenedor mongo, que ve la carpeta consultas/ en /consultas)
docker compose exec mongo mongosh sentinel --quiet --file /consultas/indices.js
```

> `cargar_datos.py` borra las colecciones **y sus índices**: cada vez que lo vuelvas a correr, repetí los índices.

Verificar que quedó todo (cantidad de documentos e índices por colección):

```bash
docker compose exec mongo mongosh sentinel --quiet --eval "db.getCollectionNames().sort().forEach(c => print(c, db[c].countDocuments(), db[c].getIndexes().map(i => i.name).join(',')))"
```

Resultado esperado: `agentes 10`, `categorias 5`, `clientes 60`, `contadores 1`, `tickets 280`, con los índices
`idx_bandeja_agente`, `uq_ticket_numero`, `idx_wildcard_campos`, `idx_categoria_creado`, `uq_agente_email` y `uq_cliente_email`.


## 6. Consultas, explain y consistencia (mongosh)

El servicio `mongo` tiene la carpeta `consultas/` montada en `/consultas`, así que se ejecutan con el `mongosh` del contenedor:

| Script | Comando |
|---|---|
| Consultas | `docker compose exec mongo mongosh sentinel --quiet --file /consultas/consultas.js` |
| Explain | `docker compose exec mongo mongosh sentinel --quiet --file /consultas/explain.js` |
| Consistencia (requiere replica set) | `docker compose exec mongo mongosh sentinel --quiet --file /consultas/consistencia.js` |

- `consultas.js` y `explain.js` solo leen.
- `consistencia.js` crea tickets de prueba (`INC-9999-*`), modifica la carga de un agente y al final deja los datos como estaban.

Para repetir todo desde cero alcanza con volver a correr la sección 5 (datos + índices).


## 7. Conectarse con MongoDB Compass

Nueva conexión con la URI:

```
mongodb://localhost:27017/?directConnection=true
```

Se ve la base `sentinel` con sus 5 colecciones (las bases `admin`, `config` y `local` son internas de MongoDB).

---

## 8. Usar la API

Con `docker compose up -d --build` la API ya está corriendo (servicio `api`) y, con los datos cargados (secciones 3 a 5),
lista para usar:

- **Swagger** (probar los endpoints desde el navegador): `http://localhost:8000/docs` → abrir un endpoint →
  *Try it out* → completar → *Execute*.
- **Health check**: `http://localhost:8000/health` → `{"status": "ok", "base": "sentinel"}` (503 si MongoDB no responde).

> Lo que hagas desde Swagger **modifica la base `sentinel`**. Para volver a los datos originales: sección 5.


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

### Configuración (variables de entorno de la API)

| Variable | Default (fuera de Compose) | Para qué |
|---|---|---|
| `MONGO_URI` | `mongodb://localhost:27017/?directConnection=true` | Dónde está MongoDB. En Compose se fija a `mongodb://mongo:27017/?replicaSet=rs0` |
| `MONGO_DB` | `sentinel` | Base a usar (los tests usan `sentinel_test`) |
| `ANIO_NUMERACION` | `2026` | Año de la numeración `INC-AAAA-NNNNNN` (contador `ticket-<año>`) |


## 9. Correr los tests

Requisito: el entorno levantado (sección 3). **No hace falta cargar datos.**

```bash
docker compose exec api python -m pytest api/tests -v
```

Resultado esperado: `53 passed`. Para correr un solo archivo:
`docker compose exec api python -m pytest api/tests/test_consistencia.py -v`.
(Sin contenedor `api`: `python -m pytest api/tests -v`, sección 4.)


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
| MongoDB no responde | 503 | el contenedor está apagado (`docker compose up -d`) |

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

- **Entrega 2**: la salida de consola de las secciones 5 y 6; se pega en `Entrega_parcial_2.md`. Los resultados de
  `explain.js` en particular **no están escritos de antemano**: son los que salgan en tu máquina.
- **Entrega 3**: la salida de `docker compose exec api python -m pytest api/tests -v` (sección 9) y las capturas de
  Swagger (sección 8, guardadas en `docs/capturas/`) ya están en `Entrega_parcial_3.md`.
- **Entrega 4 (Docker Compose)**: la salida de `docker compose ps` con los dos servicios, y la de la carga de datos y de
  los tests ejecutados dentro de los contenedores, partiendo de `docker compose down -v`.

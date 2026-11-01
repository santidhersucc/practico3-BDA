"""
Modelos Pydantic de la API de tickets.

- Entrada (*Crear, *Actualizar, ...): validan el FORMATO del request. Las reglas que dependen de la base
  (campos personalizados según la categoría, transiciones permitidas, cupo del agente) las aplica el servicio.
- Salida (TicketRespuesta, TicketResumen, PaginaTickets): describen lo que devuelve la API; los ObjectId
  se convierten a string.
"""
from datetime import datetime
from typing import Annotated, Any, Literal

from bson import ObjectId
from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field, model_validator

Prioridad = Literal["critica", "alta", "media", "baja"]
Estado = Literal["nuevo", "asignado", "en_progreso", "en_espera", "resuelto", "cerrado", "cancelado"]


def _validar_object_id(v: str) -> str:
    if not ObjectId.is_valid(v):
        raise ValueError("no es un ObjectId válido (24 caracteres hexadecimales)")
    return v


# Id recibido en el request (string que debe poder convertirse a ObjectId)
IdEntrada = Annotated[str, AfterValidator(_validar_object_id)]
# Id leído de la base (ObjectId) que se devuelve como string
IdSalida = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, ObjectId) else v)]


class _Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")       # campos desconocidos en el JSON -> 422


# ---------------------------------------------------------------- entrada

class Adjunto(BaseModel):
    nombre: str = Field(min_length=1)
    tipo: str = Field(min_length=1, description="Tipo MIME, p. ej. image/jpeg")
    tamano_kb: int = Field(ge=0)


class TicketCrear(_Entrada):
    titulo: str = Field(min_length=3, max_length=200)
    descripcion: str = Field(min_length=1)
    categoria: str = Field(description="Código de la categoría, p. ej. HW_FALLA")
    prioridad: Prioridad
    solicitante_id: IdEntrada = Field(description="_id del cliente que reporta")
    campos_personalizados: dict[str, Any] = Field(
        default_factory=dict,
        description="Dependen de la categoría; se validan contra categorias.campos_personalizados")
    etiquetas: list[str] = Field(default_factory=list)
    adjuntos: list[Adjunto] = Field(default_factory=list)


class TicketActualizar(_Entrada):
    """PATCH: solo se modifican los campos enviados."""
    titulo: str | None = Field(default=None, min_length=3, max_length=200)
    descripcion: str | None = Field(default=None, min_length=1)
    prioridad: Prioridad | None = None
    etiquetas: list[str] | None = None

    @model_validator(mode="after")
    def _al_menos_un_campo(self):
        if not self.model_dump(exclude_none=True):
            raise ValueError("hay que enviar al menos un campo para actualizar")
        return self


class CambioEstado(_Entrada):
    estado: Estado
    motivo: str | None = Field(default=None, description="Se registra en el historial")


class AutorComentario(BaseModel):
    tipo: Literal["agente", "solicitante"]
    nombre: str = Field(min_length=1)


class ComentarioCrear(_Entrada):
    autor: AutorComentario
    texto: str = Field(min_length=1, max_length=5000)


class Asignacion(_Entrada):
    agente_id: IdEntrada


# ---------------------------------------------------------------- salida

class CategoriaRef(BaseModel):
    codigo: str
    nombre: str


class SolicitanteRef(BaseModel):
    cliente_id: IdSalida
    nombre: str
    email: str
    sede: str | None = None


class AgenteRef(BaseModel):
    agente_id: IdSalida
    nombre: str


class Sla(BaseModel):
    respuesta_limite: datetime
    resolucion_limite: datetime
    primera_respuesta_en: datetime | None = None
    incumplido: bool = False


class Comentario(BaseModel):
    autor: AutorComentario
    texto: str
    fecha: datetime


class EventoHistorial(BaseModel):
    model_config = ConfigDict(extra="allow")        # cada tipo de evento puede traer datos propios
    fecha: datetime
    tipo: str
    de: str | None = None
    a: str | None = None


class Metricas(BaseModel):
    cant_comentarios: int
    reaperturas: int


class Satisfaccion(BaseModel):
    puntaje: int = Field(ge=1, le=5)
    comentario: str | None = None


class TicketResumen(BaseModel):
    """Versión liviana para listados (sin comentarios ni historial)."""
    numero: str
    titulo: str
    categoria: CategoriaRef
    prioridad: Prioridad
    estado: Estado
    solicitante: SolicitanteRef
    agente: AgenteRef | None = None
    sla: Sla
    creado: datetime
    actualizado: datetime


class TicketRespuesta(TicketResumen):
    descripcion: str
    campos_personalizados: dict[str, Any] = Field(default_factory=dict)
    etiquetas: list[str] = Field(default_factory=list)
    adjuntos: list[Adjunto] = Field(default_factory=list)
    comentarios: list[Comentario] = Field(default_factory=list)
    historial: list[EventoHistorial] = Field(default_factory=list)
    metricas: Metricas
    resuelto_en: datetime | None = None
    satisfaccion: Satisfaccion | None = None


class PaginaTickets(BaseModel):
    items: list[TicketResumen]
    total: int
    page: int
    size: int

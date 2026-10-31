from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field

PrioridadEnum = Literal["critica", "alta", "media", "baja"]
EstadoEnum = Literal["nuevo", "asignado", "en_progreso", "en_espera", "resuelto", "cerrado", "cancelado"]
TipoAutorEnum = Literal["agente", "solicitante"]

class TicketCreateSchema(BaseModel):
    titulo: str = Field(..., min_length=5, max_length=150)
    descripcion: str = Field(..., min_length=5)
    categoria_codigo: str = Field(..., examples=["HW_FALLA"])
    prioridad: PrioridadEnum
    cliente_id: str = Field(..., description="ObjectId del cliente solicitante")
    campos_personalizados: Dict[str, Any] = Field(default_factory=dict)
    etiquetas: Optional[List[str]] = None

class TicketUpdateSchema(BaseModel):
    titulo: Optional[str] = Field(None, min_length=5, max_length=150)
    descripcion: Optional[str] = Field(None, min_length=5)
    prioridad: Optional[PrioridadEnum] = None
    etiquetas: Optional[List[str]] = None
    campos_personalizados: Optional[Dict[str, Any]] = None

class AsignarAgenteSchema(BaseModel):
    agente_id: str = Field(..., description="ObjectId del agente a asignar")

class CambiarEstadoSchema(BaseModel):
    nuevo_estado: EstadoEnum

class AgregarComentarioSchema(BaseModel):
    autor_tipo: TipoAutorEnum
    autor_nombre: str = Field(..., min_length=2)
    texto: str = Field(..., min_length=1)
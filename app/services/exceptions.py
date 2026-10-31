class SentinelError(Exception):
    """Clase base para errores de negocio de Sentinel."""
    pass

class IdentificadorInvalidoError(SentinelError):
    """El formato del ID no es ni ObjectId válido ni INC-AAAA-NNNNNN."""
    pass

class RecursoNoEncontradoError(SentinelError):
    """El ticket, agente, cliente o categoría no existe en la base."""
    pass

class ValidacionDominioError(SentinelError):
    """Faltan campos personalizados obligatorios, tipo inválido o categoría inactiva."""
    pass

class TransicionEstadoInvalidaError(SentinelError):
    """El cambio de estado no está permitido por la plantilla de la categoría."""
    pass

class ConflictoNegocioError(SentinelError):
    """
    Operación válida en formato pero bloqueada por el estado actual del negocio:
    - Agente inactivo, sin habilidad para la categoría o en su capacidad máxima.
    - Intento de eliminar físicamente un ticket que no está en 'nuevo' o 'cancelado'.
    """
    pass
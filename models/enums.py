from enum import Enum

# Roles de usuario en el sistema
class UserRole(str, Enum):
    REPORTANTE = "reportante"
    ENCARGADO = "encargado"
    ADMIN = "admin"

# Estados posibles de un reporte en el flujo de trabajo
class ReportStatus(str, Enum):
    PENDIENTE = "pendiente"
    ASIGNADO = "asignado"
    EN_PROCESO = "en_proceso"
    RESUELTO = "resuelto"
    CERRADO = "cerrado"

# Niveles de prioridad para los reportes
class ReportPriority(str, Enum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"

# Tipos de actualizaciones que puede hacer un encargado o administrador
class UpdateType(str, Enum):
    AVANCE = "avance"
    OBSERVACION = "observacion"
    CAMBIO_ESTADO = "cambio_estado"
    CIERRE = "cierre"

# Tipos de notificaciones enviadas a usuarios
class NotificationType(str, Enum):
    NUEVO_REPORTE = "nuevo_reporte" 
    ASIGNACION_CASO = "asignacion_caso"
    NUEVO_AVANCE = "nuevo_avance"
    CAMBIO_ESTADO = "cambio_estado"
    CIERRE_CASO = "cierre_caso"
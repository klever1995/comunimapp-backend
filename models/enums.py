from enum import Enum

class UserRole(str, Enum):
    REPORTANTE = "reportante"
    ENCARGADO = "encargado"
    ADMIN = "admin"

class ReportStatus(str, Enum):
    PENDIENTE = "pendiente"
    ASIGNADO = "asignado"
    EN_PROCESO = "en_proceso"
    RESUELTO = "resuelto"
    CERRADO = "cerrado"

class ReportPriority(str, Enum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"

class UpdateType(str, Enum):
    AVANCE = "avance"
    OBSERVACION = "observacion"
    CAMBIO_ESTADO = "cambio_estado"
    CIERRE = "cierre"

class NotificationType(str, Enum):
    NUEVO_REPORTE = "nuevo_reporte" 
    ASIGNACION_CASO = "asignacion_caso"
    NUEVO_AVANCE = "nuevo_avance"
    CAMBIO_ESTADO = "cambio_estado"
    CIERRE_CASO = "cierre_caso"
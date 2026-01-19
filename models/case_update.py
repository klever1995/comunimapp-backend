from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.enums import UpdateType, ReportStatus

# Modelo para validación de datos al crear una actualización de caso
class CaseUpdateCreate(BaseModel):
    report_id: str
    message: str = Field(..., min_length=5)
    update_type: UpdateType = UpdateType.AVANCE
    new_status: Optional[ReportStatus] = None
    images: Optional[List[str]] = None

# Modelo completo de actualización de caso para almacenamiento en base de datos
class CaseUpdate(BaseModel):
    id: str
    report_id: str
    encargado_id: str
    message: str
    update_type: UpdateType
    new_status: Optional[ReportStatus] = None
    images: Optional[List[str]] = None
    created_at: datetime

# Modelo público para respuesta, oculta información sensible del encargado
class CaseUpdatePublic(BaseModel):
    message: str
    update_type: UpdateType
    new_status: Optional[ReportStatus] = None
    images: Optional[List[str]] = None
    created_at: datetime
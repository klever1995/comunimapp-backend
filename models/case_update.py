from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.enums import UpdateType, ReportStatus

class CaseUpdateCreate(BaseModel):
    report_id: str
    message: str = Field(..., min_length=5)
    update_type: UpdateType = UpdateType.AVANCE
    new_status: Optional[ReportStatus] = None
    images: Optional[List[str]] = None  # URLs de imágenes para esta actualización

class CaseUpdate(BaseModel):
    id: str
    report_id: str
    encargado_id: str  # Quién hizo el update
    message: str
    update_type: UpdateType
    new_status: Optional[ReportStatus] = None
    images: Optional[List[str]] = None  # URLs de imágenes subidas a Cloudinary
    created_at: datetime

# Público (para reportantes y encargados)
class CaseUpdatePublic(BaseModel):
    message: str
    update_type: UpdateType
    new_status: Optional[ReportStatus] = None
    images: Optional[List[str]] = None  # ← AÑADIDO: URLs de imágenes
    created_at: datetime
    # NOTA: No incluye encargado_id para mantener anonimato
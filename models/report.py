from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.enums import ReportStatus, ReportPriority

# Modelo para la ubicación geográfica de un reporte
class ReportLocation(BaseModel):
    latitude: float
    longitude: float
    address: Optional[str] = None
    city: Optional[str] = None

# Modelo para validar datos al crear un reporte desde el frontend
class ReportCreate(BaseModel):
    description: str = Field(..., min_length=10)
    location: ReportLocation
    images: Optional[List[str]] = None
    is_anonymous: bool = False
    priority: ReportPriority = ReportPriority.MEDIA

# Modelo completo de reporte para almacenamiento en Firestore
class Report(BaseModel):
    id: str
    description: str
    location: ReportLocation
    images: Optional[List[str]] = None
    reporter_uid: str
    is_anonymous_public: bool
    assigned_to: Optional[str] = None
    priority: ReportPriority
    status: ReportStatus = ReportStatus.PENDIENTE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None

# Modelo público para mostrar reportes con visibilidad condicional por rol
class ReportPublic(BaseModel):
    id: str
    description: str
    location: ReportLocation
    images: Optional[List[str]] = None
    priority: ReportPriority
    status: ReportStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
    assigned_to: Optional[str] = None
    reporter_uid: Optional[str] = None
    
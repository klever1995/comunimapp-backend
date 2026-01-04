from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from models.enums import ReportStatus, ReportPriority

class ReportLocation(BaseModel):
    latitude: float
    longitude: float
    address: Optional[str] = None
    city: Optional[str] = None

# Lo que envía el frontend
class ReportCreate(BaseModel):
    description: str = Field(..., min_length=10)
    location: ReportLocation
    images: Optional[List[str]] = None
    is_anonymous: bool = False  # Elige si quiere anonimato público
    priority: ReportPriority = ReportPriority.MEDIA

# Modelo para guardar en Firestore
class Report(BaseModel):
    id: str
    description: str
    location: ReportLocation
    images: Optional[List[str]] = None
    
    # ANONIMATO CORRECTO:
    reporter_uid: str  # REQUERIDO - ID real del usuario (nunca optional)
    is_anonymous_public: bool  # True = ocultar reporter_uid al público
    
    assigned_to: Optional[str] = None  # UID del encargado
    priority: ReportPriority
    status: ReportStatus = ReportStatus.PENDIENTE
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None

# Modelo para mostrar (depende del viewer)
class ReportPublic(BaseModel):
    id: str
    description: str
    location: ReportLocation
    images: Optional[List[str]] = None
    priority: ReportPriority
    status: ReportStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # CONDICIONALES:
    assigned_to: Optional[str] = None  # Solo visible para encargado/asignado y admin
    reporter_uid: Optional[str] = None  # Solo visible para ADMIN
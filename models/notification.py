from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from models.enums import NotificationType

# Modelo para crear una notificación en el sistema
class NotificationCreate(BaseModel):
    user_id: str
    report_id: Optional[str] = None
    title: str
    message: str
    notification_type: NotificationType
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_read: bool = False

# Modelo completo de notificación para almacenamiento en base de datos
class Notification(BaseModel):
    id: str
    user_id: str
    report_id: Optional[str]
    title: str
    message: str
    notification_type: NotificationType
    is_read: bool
    created_at: datetime

# Modelo público de notificación para respuestas API
class NotificationPublic(BaseModel):
    id: str
    title: str
    message: str
    notification_type: NotificationType
    is_read: bool
    created_at: datetime
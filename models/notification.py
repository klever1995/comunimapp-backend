from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from models.enums import NotificationType

class NotificationCreate(BaseModel):
    user_id: str
    report_id: Optional[str] = None
    title: str
    message: str
    notification_type: NotificationType
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_read: bool = False

class Notification(BaseModel):
    id: str
    user_id: str
    report_id: Optional[str]
    title: str
    message: str
    notification_type: NotificationType
    is_read: bool
    created_at: datetime

class NotificationPublic(BaseModel):
    id: str
    title: str
    message: str
    notification_type: NotificationType
    is_read: bool
    created_at: datetime
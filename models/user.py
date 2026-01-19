from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from models.enums import UserRole

# Modelo completo de usuario para almacenamiento en Firestore
class User(BaseModel):
    id: str
    email: EmailStr
    username: str
    role: UserRole
    is_active: bool = True
    is_verified: bool = False
    organization: Optional[str] = None
    phone: Optional[str] = None
    zone: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    auth_provider: Optional[str] = None

# Modelo para solicitud de inicio de sesión
class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)

# Modelo para registro de nuevo usuario
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    username: str = Field(..., min_length=3)
    role: UserRole = UserRole.REPORTANTE
    organization: Optional[str] = None
    phone: Optional[str] = None
    zone: Optional[str] = None

# Modelo para actualización parcial de usuario
class UserUpdate(BaseModel):
    username: Optional[str] = None
    organization: Optional[str] = None
    phone: Optional[str] = None
    zone: Optional[str] = None
    is_active: Optional[bool] = None

# Modelo público de usuario con visibilidad condicional por rol
class UserPublic(BaseModel):
    id: str
    username: str
    role: UserRole
    is_active: bool
    email: Optional[EmailStr] = None
    organization: Optional[str] = None
    phone: Optional[str] = None
    zone: Optional[str] = None
    created_at: datetime
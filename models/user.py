from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from models.enums import UserRole

# Modelo para guardar en Firestore (interno)
class User(BaseModel):
    id: str  # Firebase UID
    email: EmailStr
    username: str
    role: UserRole
    is_active: bool = True
    is_verified: bool = False
    
    # Campos específicos por rol (opcionales)
    organization: Optional[str] = None  # Para encargados
    phone: Optional[str] = None
    zone: Optional[str] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None
    
    # Datos de Firebase Auth (opcional, para sincronización)
    auth_provider: Optional[str] = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)

# Modelo para crear usuario (registro)
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    username: str = Field(..., min_length=3)
    role: UserRole = UserRole.REPORTANTE  # Valor por defecto
    
    # Solo para encargados
    organization: Optional[str] = None
    phone: Optional[str] = None
    zone: Optional[str] = None

# Modelo para actualizar usuario
class UserUpdate(BaseModel):
    username: Optional[str] = None
    organization: Optional[str] = None
    phone: Optional[str] = None
    zone: Optional[str] = None
    is_active: Optional[bool] = None

# Modelo público (varía según quién ve)
class UserPublic(BaseModel):
    id: str
    username: str
    role: UserRole
    is_active: bool
    
    # Campos condicionales
    email: Optional[EmailStr] = None  # Solo admin ve email
    organization: Optional[str] = None
    phone: Optional[str] = None
    zone: Optional[str] = None
    created_at: datetime
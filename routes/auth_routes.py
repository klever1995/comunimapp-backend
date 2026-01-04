# auth_routes.py
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse
from datetime import datetime, timedelta
import bcrypt
import jwt as pyjwt
import os
from typing import Optional
import uuid
from services.email_client import send_email

from services.firebase_client import db, auth as firebase_auth
from models.user import UserCreate, UserPublic, LoginRequest
from models.enums import UserRole

router = APIRouter(tags=["Authentication"])
security = HTTPBearer()

JWT_SECRET = os.getenv("JWT_SECRET", "supersecretkey")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = 60 * 24  # 1 día

# -------------------- Password utils -------------------- #
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# -------------------- JWT -------------------- #
def create_jwt(uid: str, role: UserRole) -> str:
    payload = {
        "sub": uid,
        "role": role.value,
        "exp": datetime.utcnow() + timedelta(minutes=JWT_EXPIRATION_MINUTES),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_jwt(token: str) -> Optional[dict]:
    try:
        payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except pyjwt.PyJWTError:
        return None


# -------------------- Dependencia para usuario autenticado -------------------- #
async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    token = credentials.credentials
    payload = decode_jwt(token)
    
    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido")
    
    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Token inválido")
    
    doc = db.collection("users").document(uid).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    user = doc.to_dict()
    user.pop("password", None)
    user.pop("verification_token", None)
    
    return user


# -------------------- Función interna para registro -------------------- #
def _register_user(user_data: UserCreate) -> dict:
    """Función interna que maneja el registro común para todos los tipos de usuario"""
    # Verificar si el email ya existe
    users_ref = db.collection("users")
    query = users_ref.where("email", "==", user_data.email).limit(1).stream()
    
    if any(query):
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    
    # Verificar si el username ya existe
    query_username = users_ref.where("username", "==", user_data.username).limit(1).stream()
    if any(query_username):
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")
    
    # 1. Crear usuario en Firebase Auth
    try:
        firebase_user = firebase_auth.create_user(
            email=user_data.email,
            password=user_data.password,
            display_name=user_data.username
        )
        uid = firebase_user.uid
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error creando usuario: {str(e)}")
    
    verification_token = str(uuid.uuid4())
    
    # 2. Determinar si necesita verificación
    needs_verification = user_data.role in [UserRole.REPORTANTE, UserRole.ENCARGADO]
    
    # 3. Preparar datos para Firestore
    user_dict = user_data.dict()
    user_dict["id"] = uid
    user_dict["password"] = hash_password(user_data.password)
    user_dict["is_verified"] = not needs_verification  # Admin = True, otros = False
    user_dict["verification_token"] = verification_token if needs_verification else None
    user_dict["is_active"] = True
    user_dict["created_at"] = datetime.utcnow()
    
    # 4. Guardar en Firestore con UID como ID del documento
    db.collection("users").document(uid).set(user_dict)
    
    # 5. Enviar email de verificación (solo para reportantes y encargados)
    if needs_verification:
        verify_link = f"http://localhost:8000/auth/verify-email?token={verification_token}"
        # Plantilla HTML similar a la que usabas antes
        email_body = f"""
        <html>
            <body>
                <h3>Bienvenido a Comunimapp</h3>
                <p>Para activar tu cuenta, haz clic en el siguiente enlace:</p>
                <a href="{verify_link}">Verificar cuenta</a>
            </body>
        </html>
        """
        send_email(user_data.email, "Verifica tu cuenta en Comunimapp", email_body)
    
    # 6. Preparar respuesta
    user_dict.pop("password")
    user_dict.pop("verification_token", None)
    return user_dict

# -------------------- Registro Reportante -------------------- #
@router.post("/register/reportante", response_model=UserPublic)
def register_reportante(user_data: UserCreate):
    # Forzar rol a REPORTANTE (ignorar lo que venga del frontend)
    user_data.role = UserRole.REPORTANTE
    user_data.organization = None
    user_data.phone = None
    user_data.zone = None
    
    user_dict = _register_user(user_data)
    return UserPublic(**user_dict)


# -------------------- Registro Encargado -------------------- #
@router.post("/register/encargado", response_model=UserPublic)
def register_encargado(user_data: UserCreate):
    # Forzar rol a ENCARGADO
    user_data.role = UserRole.ENCARGADO
    
    # Validar campos requeridos
    if not user_data.organization:
        raise HTTPException(
            status_code=400, 
            detail="Los encargados deben proporcionar una organización"
        )
    
    user_dict = _register_user(user_data)
    return UserPublic(**user_dict)


# -------------------- Registro Admin -------------------- #
@router.post("/register/admin", response_model=UserPublic)
def register_admin(user_data: UserCreate):
    # Forzar rol a ADMIN
    user_data.role = UserRole.ADMIN
    user_data.organization = None
    user_data.phone = None
    user_data.zone = None
    
    user_dict = _register_user(user_data)
    return UserPublic(**user_dict)


# -------------------- Login -------------------- #
@router.post("/login")
def login(data: LoginRequest):
    # Buscar usuario por email
    users_ref = db.collection("users")
    query = users_ref.where("email", "==", data.email).limit(1).stream()
    
    user_doc = None
    user_data = None
    for doc in query:
        user_doc = doc
        user_data = doc.to_dict()
        break
    
    if not user_doc or not user_data:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Verificar contraseña
    if not verify_password(data.password, user_data["password"]):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    
    # Verificar si la cuenta está activa
    if not user_data.get("is_active", True):
        raise HTTPException(status_code=403, detail="Cuenta desactivada")
    
    # Verificar si está verificada (solo reportantes y encargados)
    if user_data.get("role") in [UserRole.REPORTANTE, UserRole.ENCARGADO]:
        if not user_data.get("is_verified", False):
            raise HTTPException(status_code=403, detail="Cuenta no verificada")
    
    # Crear JWT con UID
    token = create_jwt(user_data["id"], UserRole(user_data["role"]))
    
    # Preparar respuesta
    user_data.pop("password", None)
    user_data.pop("verification_token", None)
    
    return {
        "user": user_data,
        "access_token": token
    }


# -------------------- Verificación Email -------------------- #
from fastapi.responses import HTMLResponse

@router.get("/verify-email", response_class=HTMLResponse)
def verify_email(token: str = Query(...)):
    users_ref = db.collection("users")
    query = users_ref.where("verification_token", "==", token).limit(1).stream()
    
    user_doc = None
    for doc in query:
        user_doc = doc
        break
    
    if not user_doc:
        return HTMLResponse("""
        <html>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h2 style="color: red;">❌ Error</h2>
            <p>El enlace de verificación no es válido o ha expirado.</p>
        </body>
        </html>
        """, status_code=400)
    
    users_ref.document(user_doc.id).update({
        "is_verified": True,
        "verification_token": None
    })
    
    return HTMLResponse("""
    <html>
    <body style="font-family: Arial; text-align: center; padding: 50px;">
        <h2 style="color: green;">✅ Verificación exitosa</h2>
        <p>Tu cuenta ha sido verificada correctamente.</p>
        <p>Ya puedes iniciar sesión en la aplicación.</p>
    </body>
    </html>
    """)

# -------------------- Verificar token (health check) -------------------- #
@router.get("/verify-token")
def verify_token(current_user: dict = Depends(get_current_user)):
    return {
        "valid": True,
        "user": {
            "id": current_user.get("id"),
            "username": current_user.get("username"),
            "role": current_user.get("role"),
            "email": current_user.get("email")
        }
    }


# -------------------- Obtener usuario actual -------------------- #
@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    """Obtiene los datos del usuario autenticado"""
    return current_user

# -------------------- Generar Custom Token de Firebase -------------------- #
@router.post("/firebase-token")
def get_firebase_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Recibe el JWT actual, lo valida y genera un Custom Token de Firebase
    para que el frontend pueda autenticarse en Firestore.
    """
    token = credentials.credentials
    payload = decode_jwt(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido")

    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Token inválido")

    # Generar Custom Token de Firebase usando el UID
    try:
        custom_token = firebase_auth.create_custom_token(uid)
        # El .decode() convierte bytes a string
        return {"firebaseCustomToken": custom_token.decode()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando token de Firebase: {str(e)}")

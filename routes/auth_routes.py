# auth_routes.py
from fastapi import APIRouter, HTTPException, Query, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import HTMLResponse
from fastapi.responses import HTMLResponse
from datetime import datetime, timedelta
import bcrypt
import jwt as pyjwt
import os
from typing import Optional
import uuid
from services.email_client import send_email
from google.cloud import firestore
from services.firebase_client import db, auth as firebase_auth
from models.user import UserCreate, UserPublic, LoginRequest
from models.enums import UserRole

# Configuración del router y seguridad para endpoints de autenticación
router = APIRouter(tags=["Authentication"])
security = HTTPBearer()

# Configuración JWT para autenticación de usuarios
JWT_SECRET = os.getenv("JWT_SECRET", "supersecretkey")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = 60 * 24  

# Funciones de utilidad para manejo seguro de contraseñas
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

# Funciones para creación y validación de tokens JWT
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
    
# Dependencia de FastAPI para obtener el usuario autenticado desde el token JWT
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


# Función interna para registro unificado de usuarios
def _register_user(user_data: UserCreate) -> dict:
    """Función interna que maneja el registro común para todos los tipos de usuario"""
    users_ref = db.collection("users")
    query = users_ref.where("email", "==", user_data.email).limit(1).stream()
    
    if any(query):
        raise HTTPException(status_code=400, detail="El email ya está registrado")
    
    query_username = users_ref.where("username", "==", user_data.username).limit(1).stream()
    if any(query_username):
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")
    
    # Creación en Firebase Authentication
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
    
    # Solo reportantes y encargados requieren verificación por email
    needs_verification = user_data.role in [UserRole.REPORTANTE, UserRole.ENCARGADO]
    
    # Preparar documento de usuario para Firestore
    user_dict = user_data.dict()
    user_dict["id"] = uid
    user_dict["password"] = hash_password(user_data.password)
    user_dict["is_verified"] = not needs_verification
    user_dict["verification_token"] = verification_token if needs_verification else None
    user_dict["is_active"] = True
    user_dict["created_at"] = datetime.utcnow()
    
    db.collection("users").document(uid).set(user_dict)
    
    # Enviar email de verificación si es necesario
    if needs_verification:
        verify_link = f"http://localhost:8000/auth/verify-email?token={verification_token}"
        email_body = f"""
        <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ text-align: center; padding: 20px 0; }}
                    .logo {{ max-width: 200px; height: auto; }}
                    .content {{ padding: 30px 0; text-align: center; }}
                    .button {{ display: inline-block; padding: 14px 28px; background-color: #4CAF50; color: white; 
                             text-decoration: none; border-radius: 6px; font-weight: bold; font-size: 16px; }}
                    .footer {{ text-align: center; padding-top: 20px; border-top: 1px solid #eee; color: #666; font-size: 12px; }}
                </style>
            </head>
            <body>
                <div class="header">
                    <img src="https://res.cloudinary.com/dnz1ohunj/image/upload/v1768769009/bienvenida_loweem.png" alt="ComuniMapp Logo" class="logo">
                    <h2>Sistema de Reportes Ciudadanos</h2>
                </div>
                <div class="content">
                    <h3>¡Bienvenido a ComuniMapp!</h3>
                    <p>Hola <strong>{user_data.username}</strong>,</p>
                    <p>Para activar tu cuenta, haz clic en el siguiente botón:</p>
                    <br>
                    <a href="{verify_link}" class="button">Activar Mi Cuenta</a>
                    <br><br>
                    <p><small>Este enlace expirará en 24 horas.</small></p>
                </div>
                <div class="footer">
                    <p>© {datetime.now().year} ComuniMapp</p>
                </div>
            </body>
        </html>
        """
        send_email(user_data.email, "Activa tu cuenta en ComuniMapp", email_body)
    
    # Limpiar datos sensibles antes de retornar
    user_dict.pop("password")
    user_dict.pop("verification_token", None)
    return user_dict

# Endpoint para registro de usuarios con rol de reportante
@router.post("/register/reportante", response_model=UserPublic)
def register_reportante(user_data: UserCreate):
    user_data.role = UserRole.REPORTANTE
    user_data.organization = None
    user_data.phone = None
    user_data.zone = None
    
    user_dict = _register_user(user_data)
    return UserPublic(**user_dict)


# Endpoint para registro de usuarios con rol de encargado
@router.post("/register/encargado", response_model=UserPublic)
def register_encargado(user_data: UserCreate):
    user_data.role = UserRole.ENCARGADO
    
    if not user_data.organization:
        raise HTTPException(
            status_code=400, 
            detail="Los encargados deben proporcionar una organización"
        )
    
    user_dict = _register_user(user_data)
    return UserPublic(**user_dict)

# Endpoint para registro de usuarios con rol de administrador
@router.post("/register/admin", response_model=UserPublic)
def register_admin(user_data: UserCreate):
    user_data.role = UserRole.ADMIN
    user_data.organization = None
    user_data.phone = None
    user_data.zone = None
    
    user_dict = _register_user(user_data)
    return UserPublic(**user_dict)

# Endpoint para autenticación de usuarios existentes
@router.post("/login")
def login(data: LoginRequest):
    # Buscar usuario por dirección de email en Firestore
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
    
    # Verificación de contraseña utilizando bcrypt
    if not verify_password(data.password, user_data["password"]):
        raise HTTPException(status_code=401, detail="Contraseña incorrecta")
    
    # Validación de estado de la cuenta (activa/inactiva)
    if not user_data.get("is_active", True):
        raise HTTPException(status_code=403, detail="Cuenta desactivada")
    
    # Verificación de email para roles reportante y encargado
    if user_data.get("role") in [UserRole.REPORTANTE, UserRole.ENCARGADO]:
        if not user_data.get("is_verified", False):
            raise HTTPException(status_code=403, detail="Cuenta no verificada")
    
    # Generación de token JWT para sesión autenticada
    token = create_jwt(user_data["id"], UserRole(user_data["role"]))
    
    # Preparar respuesta eliminando datos sensibles
    user_data.pop("password", None)
    user_data.pop("verification_token", None)
    
    return {
        "user": user_data,
        "access_token": token
    }

# Endpoint para verificación de direcciones de email mediante token
@router.get("/verify-email", response_class=HTMLResponse)
def verify_email(token: str = Query(...)):
    # Buscar usuario con el token de verificación proporcionado
    users_ref = db.collection("users")
    query = users_ref.where("verification_token", "==", token).limit(1).stream()
    
    user_doc = None
    for doc in query:
        user_doc = doc
        break
    
    # Mostrar página de error si el token no es válido o ha expirado
    if not user_doc:
        return HTMLResponse("""
        <html>
        <body style="font-family: Arial; text-align: center; padding: 50px;">
            <h2 style="color: red;"> Error</h2>
            <p>El enlace de verificación no es válido o ha expirado.</p>
        </body>
        </html>
        """, status_code=400)
    
    # Actualizar estado de verificación del usuario en Firestore
    users_ref.document(user_doc.id).update({
        "is_verified": True,
        "verification_token": None
    })
    
    # Mostrar página de confirmación de verificación exitosa
    return HTMLResponse("""
    <html>
    <body style="font-family: Arial; text-align: center; padding: 50px;">
        <h2 style="color: green;"> Verificación exitosa</h2>
        <p>Tu cuenta ha sido verificada correctamente.</p>
        <p>Ya puedes iniciar sesión en la aplicación.</p>
    </body>
    </html>
    """)

# Endpoint para verificación de validez del token JWT (health check)
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

# Endpoint para obtener los datos completos del usuario autenticado
@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return current_user

# Endpoint para generación de Custom Tokens de Firebase para autenticación en Firestore
@router.post("/firebase-token")
def get_firebase_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):

    token = credentials.credentials
    payload = decode_jwt(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Token inválido")

    uid = payload.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Token inválido")

    # Generar Custom Token de Firebase usando el UID del usuario
    try:
        custom_token = firebase_auth.create_custom_token(uid)
        return {"firebaseCustomToken": custom_token.decode()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando token de Firebase: {str(e)}")


# Endpoint para registro de tokens FCM para notificaciones push
@router.post("/register-fcm-token")
def register_fcm_token(fcm_data: dict, credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_jwt(token)
    if not payload: raise HTTPException(401, "Token inválido")
    
    user_id = payload.get("sub")
    request_user_id = fcm_data.get("user_id")
    if request_user_id != user_id: raise HTTPException(403, "No autorizado")
    
    fcm_token = fcm_data.get("fcm_token")
    print(f"DEBUG - Registrando FCM token: user_id={user_id}, fcm_token={fcm_token}")
    if not fcm_token: raise HTTPException(400, "fcm_token requerido")
    
    # Preparar datos del token para almacenamiento en Firestore
    token_data = {
        "user_id": user_id,
        "fcm_token": fcm_token,
        "device_type": fcm_data.get("device_type", "unknown"),
        "registered_at": datetime.utcnow(),
        "is_active": True,
        "last_updated": datetime.utcnow()
    }
    
    # Generar ID único para el token usando hash MD5
    import hashlib
    token_hash = hashlib.md5(fcm_token.encode()).hexdigest()
    token_id = f"{user_id}_{token_hash}"
    
    # Almacenar token en colección específica de FCM
    db.collection("fcm_tokens").document(token_id).set(token_data)
    
    # Actualizar referencia de tokens en el documento del usuario
    user_ref = db.collection("users").document(user_id)
    user_ref.update({
        "fcm_tokens": [fcm_token], 
        "has_fcm_token": True,
        "last_fcm_update": datetime.utcnow()
    })
    
    return {"success": True, "token_id": token_id}

# Endpoint para eliminación de tokens FCM cuando un dispositivo se desregistra
@router.delete("/remove-fcm-token")
def remove_fcm_token(fcm_token: str = Query(...), credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = decode_jwt(token)
    if not payload: raise HTTPException(401, "Token inválido")
    
    user_id = payload.get("sub")
    tokens_ref = db.collection("fcm_tokens")
    query = tokens_ref.where("user_id", "==", user_id).where("fcm_token", "==", fcm_token).limit(1).stream()
    
    deleted = False
    for doc in query:
        doc.reference.delete()
        deleted = True
        break
    
    # Actualizar array de tokens del usuario si se eliminó exitosamente
    if deleted:
        user_ref = db.collection("users").document(user_id)
        user_ref.update({"fcm_tokens": firestore.ArrayRemove([fcm_token])})
        remaining = user_ref.get().to_dict().get("fcm_tokens", [])
        if not remaining: user_ref.update({"has_fcm_token": False})
    
    return {"success": deleted}
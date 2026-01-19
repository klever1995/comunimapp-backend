# user_routes.py
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import datetime

from services.firebase_client import db
from models.user import UserPublic, UserUpdate
from models.enums import UserRole

from routes.auth_routes import get_current_user

# Configuración del router
router = APIRouter(tags=["Users"])

# Funciones auxiliares para autorización y control de acceso
def is_admin(current_user: dict) -> bool:
    return current_user.get("role") == UserRole.ADMIN

def can_manage_user(current_user: dict, target_user_id: str) -> bool:
    if is_admin(current_user):
        return True
    return current_user.get("id") == target_user_id

# Endpoint para obtener el perfil del usuario autenticado
@router.get("/me", response_model=UserPublic)
def get_my_profile(current_user: dict = Depends(get_current_user)):
    return current_user


# Endpoint para actualización del perfil del usuario autenticado
@router.put("/me", response_model=UserPublic)
def update_my_profile(
    update_data: UserUpdate,
    current_user: dict = Depends(get_current_user)
):

    user_id = current_user.get("id")
    doc_ref = db.collection("users").document(user_id)
    
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    user_data = doc.to_dict()
    
    # Validaciones específicas para usuarios con rol de encargado
    if user_data.get("role") == UserRole.ENCARGADO:
        if update_data.organization == "":
            raise HTTPException(
                status_code=400, 
                detail="Los encargados deben tener organización"
            )
    
    update_dict = update_data.dict(exclude_unset=True)
    update_dict["updated_at"] = datetime.utcnow()
    
    # Verificación de unicidad del nombre de usuario
    if "username" in update_dict:
        users_ref = db.collection("users")
        query = users_ref.where("username", "==", update_dict["username"]).limit(1).stream()
        for existing_doc in query:
            if existing_doc.id != user_id:
                raise HTTPException(status_code=400, detail="Nombre de usuario ya en uso")
    
    doc_ref.update(update_dict)
    
    updated_doc = doc_ref.get()
    updated_data = updated_doc.to_dict()
    
    # Preparación de respuesta completa del perfil actualizado
    response_data = {
        "id": updated_data.get("id"),
        "username": updated_data.get("username"),
        "email": updated_data.get("email"),
        "role": updated_data.get("role"),
        "is_active": updated_data.get("is_active", True),
        "is_verified": updated_data.get("is_verified", False),
        "created_at": updated_data.get("created_at")
    }
    
    if updated_data.get("role") == UserRole.ENCARGADO:
        response_data["organization"] = updated_data.get("organization")
        response_data["phone"] = updated_data.get("phone")
        response_data["zone"] = updated_data.get("zone")
    
    return UserPublic(**response_data)


# Endpoint para obtener información de usuario por identificador
@router.get("/{user_id}", response_model=UserPublic)
def get_user(
    user_id: str,
    current_user: dict = Depends(get_current_user)
):

    doc = db.collection("users").document(user_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    user_data = doc.to_dict()
    current_user_id = current_user.get("id")
    is_admin_user = is_admin(current_user)
    is_own_profile = current_user_id == user_id
    
    # Construcción de respuesta base con datos públicos
    response_data = {
        "id": user_data.get("id"),
        "username": user_data.get("username"),
        "role": user_data.get("role"),
        "is_active": user_data.get("is_active", True),
        "created_at": user_data.get("created_at")
    }
    
    # Control de visibilidad para datos sensibles (email, verificación)
    if is_admin_user or is_own_profile:
        response_data["email"] = user_data.get("email")
        response_data["is_verified"] = user_data.get("is_verified", False)
    
    # Campos específicos para usuarios con rol de encargado
    if user_data.get("role") == UserRole.ENCARGADO:
        response_data["organization"] = user_data.get("organization")
        response_data["phone"] = user_data.get("phone")
        response_data["zone"] = user_data.get("zone")
    
    return UserPublic(**response_data)


# Endpoint para listar usuarios del sistema con filtros opcionales
@router.get("/", response_model=List[UserPublic])
def list_users(
    role: Optional[UserRole] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: dict = Depends(get_current_user)
):

    users_ref = db.collection("users")
    
    # Aplicación de filtros por rol y estado de actividad
    if role:
        users_ref = users_ref.where("role", "==", role.value)
    if is_active is not None:
        users_ref = users_ref.where("is_active", "==", is_active)
    
    users = []
    current_user_id = current_user.get("id")
    is_admin_user = is_admin(current_user)
    
    for doc in users_ref.stream():
        user_data = doc.to_dict()
        user_id = user_data.get("id")
        
        is_own_profile = current_user_id == user_id
        
        # Estructura base de datos públicos del usuario
        user_public = {
            "id": user_id,
            "username": user_data.get("username"),
            "role": user_data.get("role"),
            "is_active": user_data.get("is_active", True),
            "created_at": user_data.get("created_at")
        }
        
        # Control de acceso a información sensible por rol
        if is_admin_user or is_own_profile:
            user_public["email"] = user_data.get("email")
            user_public["is_verified"] = user_data.get("is_verified", False)
        
        # Inclusión de campos específicos para usuarios encargados
        if user_data.get("role") == UserRole.ENCARGADO:
            user_public["organization"] = user_data.get("organization")
            user_public["phone"] = user_data.get("phone")
            user_public["zone"] = user_data.get("zone")
        
        users.append(UserPublic(**user_public))
    
    return users

# Endpoint para actualización de usuarios por identificador con control de permisos
@router.put("/{user_id}", response_model=UserPublic)
def update_user(
    user_id: str,
    update_data: UserUpdate,
    current_user: dict = Depends(get_current_user)
):

    # Verificación de autorización para modificar el usuario objetivo
    if not can_manage_user(current_user, user_id):
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para actualizar este usuario"
        )
    
    doc_ref = db.collection("users").document(user_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    user_data = doc.to_dict()
    
    # Restricciones de permisos para usuarios no administradores
    if not is_admin(current_user):
        if current_user.get("id") != user_id:
            raise HTTPException(
                status_code=403, 
                detail="Solo puedes actualizar tu propio perfil"
            )
        
        if "role" in update_data.dict(exclude_unset=True):
            raise HTTPException(
                status_code=403, 
                detail="No puedes cambiar tu rol"
            )
    
    # Validación de campos obligatorios para usuarios encargados
    if user_data.get("role") == UserRole.ENCARGADO:
        if update_data.organization == "":
            raise HTTPException(
                status_code=400, 
                detail="Los encargados deben tener organización"
            )
    
    update_dict = update_data.dict(exclude_unset=True)
    update_dict["updated_at"] = datetime.utcnow()
    
    # Verificación de unicidad del nombre de usuario en actualizaciones
    if "username" in update_dict:
        users_ref = db.collection("users")
        query = users_ref.where("username", "==", update_dict["username"]).limit(1).stream()
        for existing_doc in query:
            if existing_doc.id != user_id:
                raise HTTPException(status_code=400, detail="Nombre de usuario ya en uso")
    
    doc_ref.update(update_dict)
    
    # Obtención del usuario actualizado para construcción de respuesta
    updated_doc = doc_ref.get()
    updated_data = updated_doc.to_dict()
    
    response_data = {
        "id": updated_data.get("id"),
        "username": updated_data.get("username"),
        "role": updated_data.get("role"),
        "is_active": updated_data.get("is_active", True),
        "created_at": updated_data.get("created_at")
    }
    
    # Control de visibilidad para datos sensibles según permisos
    if is_admin(current_user) or current_user.get("id") == user_id:
        response_data["email"] = updated_data.get("email")
        response_data["is_verified"] = updated_data.get("is_verified", False)
    
    # Inclusión de campos específicos para perfiles de encargado
    if updated_data.get("role") == UserRole.ENCARGADO:
        response_data["organization"] = updated_data.get("organization")
        response_data["phone"] = updated_data.get("phone")
        response_data["zone"] = updated_data.get("zone")
    
    return UserPublic(**response_data)


# Endpoint para eliminación de usuarios del sistema con validación de seguridad
@router.delete("/{user_id}")
def delete_user(
    user_id: str,
    current_user: dict = Depends(get_current_user)
):

    # Validación de autorización para operación de eliminación
    if not can_manage_user(current_user, user_id):
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para eliminar este usuario"
        )
    
    doc_ref = db.collection("users").document(user_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Restricción de seguridad para evitar auto-eliminación de administradores
    if is_admin(current_user) and current_user.get("id") == user_id:
        raise HTTPException(
            status_code=400, 
            detail="Los administradores no pueden eliminar su propia cuenta"
        )
    
    user_data = doc.to_dict()
    
    # Eliminación del usuario en Firebase Authentication
    try:
        from services.firebase_client import auth as firebase_auth
        firebase_auth.delete_user(user_id)
    except Exception as e:
        print(f"Advertencia: No se pudo eliminar de Firebase Auth: {e}")
    
    # Eliminación del documento de usuario en Firestore
    doc_ref.delete()
    
    return {"message": "Usuario eliminado correctamente"}


# Endpoint para cambio de estado activo/inactivo de usuarios
@router.patch("/{user_id}/toggle-active")
def toggle_user_active(
    user_id: str,
    is_active: bool = Query(...),
    current_user: dict = Depends(get_current_user)
):

    # Verificación de permisos para modificación de estado de usuario
    if not can_manage_user(current_user, user_id):
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para cambiar el estado de este usuario"
        )
    
    # Restricción de seguridad para evitar auto-desactivación
    if not is_admin(current_user) and not is_active:
        raise HTTPException(
            status_code=400, 
            detail="No puedes desactivar tu propia cuenta"
        )
    
    doc_ref = db.collection("users").document(user_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Actualización del estado de actividad en Firestore
    doc_ref.update({
        "is_active": is_active,
        "updated_at": datetime.utcnow()
    })
    
    return {"message": f"Usuario {'activado' if is_active else 'desactivado'} correctamente"}
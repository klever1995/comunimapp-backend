# user_routes.py
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import List, Optional
from datetime import datetime

from services.firebase_client import db
from models.user import UserPublic, UserUpdate
from models.enums import UserRole

# Importar dependencia de autenticación desde auth_routes
from routes.auth_routes import get_current_user

router = APIRouter(tags=["Users"])


# -------------------- Funciones de autorización -------------------- #
def is_admin(current_user: dict) -> bool:
    """Verifica si el usuario actual es administrador"""
    return current_user.get("role") == UserRole.ADMIN

def can_manage_user(current_user: dict, target_user_id: str) -> bool:
    """
    Verifica si el usuario actual puede gestionar al usuario objetivo.
    Reglas:
    - Admin puede gestionar a cualquier usuario
    - Usuarios no-admin solo pueden gestionarse a sí mismos
    """
    if is_admin(current_user):
        return True
    return current_user.get("id") == target_user_id


# -------------------- Obtener perfil propio -------------------- #
@router.get("/me", response_model=UserPublic)
def get_my_profile(current_user: dict = Depends(get_current_user)):
    """
    Obtiene el perfil del usuario autenticado.
    Devuelve todos los datos del usuario (incluyendo email).
    """
    return current_user


# -------------------- Actualizar perfil propio -------------------- #
@router.put("/me", response_model=UserPublic)
def update_my_profile(
    update_data: UserUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Actualiza el perfil del usuario autenticado.
    """
    user_id = current_user.get("id")
    doc_ref = db.collection("users").document(user_id)
    
    # Verificar que el usuario existe
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    user_data = doc.to_dict()
    
    # Validaciones específicas por rol
    if user_data.get("role") == UserRole.ENCARGADO:
        # Si es encargado y quieren quitar organización
        if update_data.organization == "":
            raise HTTPException(
                status_code=400, 
                detail="Los encargados deben tener organización"
            )
    
    # Preparar datos a actualizar
    update_dict = update_data.dict(exclude_unset=True)
    update_dict["updated_at"] = datetime.utcnow()
    
    # Si se actualiza username, verificar que no exista
    if "username" in update_dict:
        # Verificar que el nuevo username no esté en uso por otro usuario
        users_ref = db.collection("users")
        query = users_ref.where("username", "==", update_dict["username"]).limit(1).stream()
        for existing_doc in query:
            if existing_doc.id != user_id:  # Si otro usuario ya tiene ese username
                raise HTTPException(status_code=400, detail="Nombre de usuario ya en uso")
    
    # Actualizar en Firestore
    doc_ref.update(update_dict)
    
    # Obtener usuario actualizado
    updated_doc = doc_ref.get()
    updated_data = updated_doc.to_dict()
    
    # Preparar respuesta con todos los datos (propio usuario)
    response_data = {
        "id": updated_data.get("id"),
        "username": updated_data.get("username"),
        "email": updated_data.get("email"),
        "role": updated_data.get("role"),
        "is_active": updated_data.get("is_active", True),
        "is_verified": updated_data.get("is_verified", False),
        "created_at": updated_data.get("created_at")
    }
    
    # Campos de encargado
    if updated_data.get("role") == UserRole.ENCARGADO:
        response_data["organization"] = updated_data.get("organization")
        response_data["phone"] = updated_data.get("phone")
        response_data["zone"] = updated_data.get("zone")
    
    return UserPublic(**response_data)


# -------------------- Obtener usuario por ID -------------------- #
@router.get("/{user_id}", response_model=UserPublic)
def get_user(
    user_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Obtiene un usuario por ID.
    - Admin: Ve todos los campos de cualquier usuario
    - Usuario mismo: Ve todos sus propios campos
    - Otros: Solo ve datos públicos
    """
    doc = db.collection("users").document(user_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    user_data = doc.to_dict()
    current_user_id = current_user.get("id")
    is_admin_user = is_admin(current_user)
    is_own_profile = current_user_id == user_id
    
    # Construir respuesta base
    response_data = {
        "id": user_data.get("id"),
        "username": user_data.get("username"),
        "role": user_data.get("role"),
        "is_active": user_data.get("is_active", True),
        "created_at": user_data.get("created_at")
    }
    
    # Mostrar email e is_verified solo a admin o al propio usuario
    if is_admin_user or is_own_profile:
        response_data["email"] = user_data.get("email")
        response_data["is_verified"] = user_data.get("is_verified", False)
    
    # Campos de encargado
    if user_data.get("role") == UserRole.ENCARGADO:
        response_data["organization"] = user_data.get("organization")
        response_data["phone"] = user_data.get("phone")
        response_data["zone"] = user_data.get("zone")
    
    return UserPublic(**response_data)


# -------------------- Listar usuarios -------------------- #
@router.get("/", response_model=List[UserPublic])
def list_users(
    role: Optional[UserRole] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Lista usuarios con filtros opcionales.
    - Admin: Ve todos los campos de todos los usuarios
    - No-admin: Solo ve datos públicos de otros usuarios
    """
    users_ref = db.collection("users")
    
    # Aplicar filtros
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
        
        # Construir respuesta
        user_public = {
            "id": user_id,
            "username": user_data.get("username"),
            "role": user_data.get("role"),
            "is_active": user_data.get("is_active", True),
            "created_at": user_data.get("created_at")
        }
        
        # Mostrar email e is_verified solo a admin o al propio usuario
        if is_admin_user or is_own_profile:
            user_public["email"] = user_data.get("email")
            user_public["is_verified"] = user_data.get("is_verified", False)
        
        # Campos de encargado
        if user_data.get("role") == UserRole.ENCARGADO:
            user_public["organization"] = user_data.get("organization")
            user_public["phone"] = user_data.get("phone")
            user_public["zone"] = user_data.get("zone")
        
        users.append(UserPublic(**user_public))
    
    return users


# -------------------- Actualizar usuario por ID -------------------- #
@router.put("/{user_id}", response_model=UserPublic)
def update_user(
    user_id: str,
    update_data: UserUpdate,
    current_user: dict = Depends(get_current_user)
):
    """
    Actualiza un usuario por ID.
    - Admin: Puede actualizar cualquier usuario
    - No-admin: Solo puede actualizar su propio perfil
    """
    # Verificar permisos
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
    
    # Validaciones específicas por rol (solo admin puede cambiar roles)
    if not is_admin(current_user):
        # No-admin no puede cambiar campos sensibles de otros usuarios
        if current_user.get("id") != user_id:
            raise HTTPException(
                status_code=403, 
                detail="Solo puedes actualizar tu propio perfil"
            )
        
        # No-admin no puede cambiar su propio rol
        if "role" in update_data.dict(exclude_unset=True):
            raise HTTPException(
                status_code=403, 
                detail="No puedes cambiar tu rol"
            )
    
    # Validaciones para encargados
    if user_data.get("role") == UserRole.ENCARGADO:
        if update_data.organization == "":
            raise HTTPException(
                status_code=400, 
                detail="Los encargados deben tener organización"
            )
    
    # Preparar datos a actualizar
    update_dict = update_data.dict(exclude_unset=True)
    update_dict["updated_at"] = datetime.utcnow()
    
    # Si se actualiza username, verificar que no exista
    if "username" in update_dict:
        users_ref = db.collection("users")
        query = users_ref.where("username", "==", update_dict["username"]).limit(1).stream()
        for existing_doc in query:
            if existing_doc.id != user_id:
                raise HTTPException(status_code=400, detail="Nombre de usuario ya en uso")
    
    # Actualizar en Firestore
    doc_ref.update(update_dict)
    
    # Obtener usuario actualizado
    updated_doc = doc_ref.get()
    updated_data = updated_doc.to_dict()
    
    # Construir respuesta
    response_data = {
        "id": updated_data.get("id"),
        "username": updated_data.get("username"),
        "role": updated_data.get("role"),
        "is_active": updated_data.get("is_active", True),
        "created_at": updated_data.get("created_at")
    }
    
    # Solo admin o el propio usuario ve email
    if is_admin(current_user) or current_user.get("id") == user_id:
        response_data["email"] = updated_data.get("email")
        response_data["is_verified"] = updated_data.get("is_verified", False)
    
    # Campos de encargado
    if updated_data.get("role") == UserRole.ENCARGADO:
        response_data["organization"] = updated_data.get("organization")
        response_data["phone"] = updated_data.get("phone")
        response_data["zone"] = updated_data.get("zone")
    
    return UserPublic(**response_data)


# -------------------- Eliminar usuario -------------------- #
@router.delete("/{user_id}")
def delete_user(
    user_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Elimina un usuario.
    - Admin: Puede eliminar cualquier usuario
    - No-admin: Solo puede eliminar su propia cuenta
    """
    # Verificar permisos
    if not can_manage_user(current_user, user_id):
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para eliminar este usuario"
        )
    
    doc_ref = db.collection("users").document(user_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Admin no puede eliminarse a sí mismo
    if is_admin(current_user) and current_user.get("id") == user_id:
        raise HTTPException(
            status_code=400, 
            detail="Los administradores no pueden eliminar su propia cuenta"
        )
    
    user_data = doc.to_dict()
    
    try:
        # Eliminar de Firebase Auth
        from services.firebase_client import auth as firebase_auth
        firebase_auth.delete_user(user_id)
    except Exception as e:
        print(f"Advertencia: No se pudo eliminar de Firebase Auth: {e}")
    
    # Eliminar de Firestore
    doc_ref.delete()
    
    return {"message": "Usuario eliminado correctamente"}


# -------------------- Cambiar estado activo/inactivo -------------------- #
@router.patch("/{user_id}/toggle-active")
def toggle_user_active(
    user_id: str,
    is_active: bool = Query(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Activa o desactiva un usuario.
    - Admin: Puede activar/desactivar cualquier usuario
    - No-admin: Solo puede cambiar su propio estado
    """
    # Verificar permisos
    if not can_manage_user(current_user, user_id):
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para cambiar el estado de este usuario"
        )
    
    # No permitir desactivar la cuenta propia
    if not is_admin(current_user) and not is_active:
        raise HTTPException(
            status_code=400, 
            detail="No puedes desactivar tu propia cuenta"
        )
    
    doc_ref = db.collection("users").document(user_id)
    doc = doc_ref.get()
    
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    doc_ref.update({
        "is_active": is_active,
        "updated_at": datetime.utcnow()
    })
    
    return {"message": f"Usuario {'activado' if is_active else 'desactivado'} correctamente"}
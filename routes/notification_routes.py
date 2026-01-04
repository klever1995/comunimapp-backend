# notification_routes.py
from fastapi import APIRouter, HTTPException, Depends, Query, status
from typing import List, Optional
from datetime import datetime, timedelta

from services.firebase_client import db
from models.notification import Notification, NotificationPublic
from models.enums import UserRole, NotificationType
from routes.auth_routes import get_current_user

router = APIRouter(tags=["Notifications"])


# -------------------- Funciones auxiliares -------------------- #
def is_admin(current_user: dict) -> bool:
    return current_user.get("role") == UserRole.ADMIN

def can_view_notification(current_user: dict, notification_data: dict) -> bool:
    """
    Verifica si el usuario actual puede ver una notificación.
    Reglas:
    - Cada usuario solo puede ver sus propias notificaciones
    - Admin no puede ver notificaciones de otros usuarios
    """
    user_id = current_user.get("id")
    notification_user_id = notification_data.get("user_id")
    
    return user_id == notification_user_id


# -------------------- Listar notificaciones -------------------- #
@router.get("/", response_model=List[NotificationPublic])
def list_notifications(
    notification_type: Optional[NotificationType] = Query(None),
    is_read: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user)
):
    """
    Lista las notificaciones del usuario autenticado.
    Cada usuario solo puede ver sus propias notificaciones.
    """
    user_id = current_user.get("id")
    
    # Construir consulta base
    notifications_ref = db.collection("notifications").where("user_id", "==", user_id)
    
    # Aplicar filtros adicionales
    if notification_type:
        notifications_ref = notifications_ref.where("notification_type", "==", notification_type.value)
    
    if is_read is not None:
        notifications_ref = notifications_ref.where("is_read", "==", is_read)
    
    # Obtener notificaciones con paginación
    notifications = []
    try:
        # Ordenar por fecha de creación (más reciente primero)
        query = notifications_ref.order_by("created_at", direction="DESCENDING")
        
        # Aplicar offset y limit
        if offset > 0:
            # Para offset necesitamos una consulta separada
            offset_query = query.limit(offset)
            offset_docs = list(offset_query.stream())
            if len(offset_docs) >= offset:
                last_doc = offset_docs[-1]
                query = query.start_after(last_doc)
        
        docs = query.limit(limit).stream()
        
        for doc in docs:
            notification_data = doc.to_dict()
            notification_data["id"] = doc.id
            
            # Convertir Firestore Timestamp a datetime si es necesario
            if hasattr(notification_data.get("created_at"), 'timestamp'):
                notification_data["created_at"] = notification_data["created_at"].timestamp()
            
            notifications.append(NotificationPublic(**notification_data))
            
    except Exception as e:
        print(f"Error consultando notificaciones: {e}")
        # Si hay error con la consulta compleja, hacer una simple
        notifications_ref = db.collection("notifications").where("user_id", "==", user_id)
        docs = notifications_ref.stream()
        notifications = []
        for doc in docs:
            notification_data = doc.to_dict()
            notification_data["id"] = doc.id
            if hasattr(notification_data.get("created_at"), 'timestamp'):
                notification_data["created_at"] = notification_data["created_at"].timestamp()
            notifications.append(NotificationPublic(**notification_data))
        
        # Ordenar manualmente por fecha
        notifications.sort(key=lambda x: x.created_at, reverse=True)
        # Aplicar límite manualmente
        notifications = notifications[offset:offset + limit]
    
    return notifications


# -------------------- Obtener notificación específica -------------------- #
@router.get("/{notification_id}", response_model=NotificationPublic)
def get_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Obtiene una notificación específica por ID.
    El usuario solo puede ver sus propias notificaciones.
    """
    # Obtener la notificación
    notification_doc = db.collection("notifications").document(notification_id).get()
    
    if not notification_doc.exists:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    
    notification_data = notification_doc.to_dict()
    notification_data["id"] = notification_id
    
    # Verificar permisos
    if not can_view_notification(current_user, notification_data):
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para ver esta notificación"
        )
    
    # Convertir Firestore Timestamp si es necesario
    if hasattr(notification_data.get("created_at"), 'timestamp'):
        notification_data["created_at"] = notification_data["created_at"].timestamp()
    
    return NotificationPublic(**notification_data)


# -------------------- Marcar notificación como leída -------------------- #
@router.patch("/{notification_id}/read", response_model=NotificationPublic)
def mark_as_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Marca una notificación como leída.
    El usuario solo puede marcar sus propias notificaciones.
    """
    notification_ref = db.collection("notifications").document(notification_id)
    notification_doc = notification_ref.get()
    
    if not notification_doc.exists:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    
    notification_data = notification_doc.to_dict()
    
    # Verificar permisos
    if not can_view_notification(current_user, notification_data):
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para modificar esta notificación"
        )
    
    # Verificar si ya está leída
    if notification_data.get("is_read", False):
        # Ya está leída, devolver la actual
        notification_data["id"] = notification_id
        if hasattr(notification_data.get("created_at"), 'timestamp'):
            notification_data["created_at"] = notification_data["created_at"].timestamp()
        return NotificationPublic(**notification_data)
    
    # Marcar como leída
    update_time = datetime.utcnow()
    notification_ref.update({
        "is_read": True,
        "updated_at": update_time
    })
    
    # Obtener notificación actualizada
    updated_doc = notification_ref.get()
    updated_data = updated_doc.to_dict()
    updated_data["id"] = notification_id
    
    # Convertir Firestore Timestamp si es necesario
    if hasattr(updated_data.get("created_at"), 'timestamp'):
        updated_data["created_at"] = updated_data["created_at"].timestamp()
    
    return NotificationPublic(**updated_data)


# -------------------- Marcar todas como leídas -------------------- #
@router.post("/mark-all-read")
def mark_all_as_read(
    current_user: dict = Depends(get_current_user)
):
    """
    Marca todas las notificaciones no leídas del usuario como leídas.
    """
    user_id = current_user.get("id")
    
    try:
        # Buscar todas las notificaciones no leídas del usuario
        notifications_ref = db.collection("notifications").where("user_id", "==", user_id).where("is_read", "==", False)
        
        update_time = datetime.utcnow()
        updated_count = 0
        
        # Usar batch para actualizar en lote (máximo 500 por batch)
        batch = db.batch()
        batch_count = 0
        
        for doc in notifications_ref.stream():
            notification_ref = db.collection("notifications").document(doc.id)
            batch.update(notification_ref, {
                "is_read": True,
                "updated_at": update_time
            })
            updated_count += 1
            batch_count += 1
            
            # Firestore limita a 500 operaciones por batch
            if batch_count >= 500:
                batch.commit()
                batch = db.batch()
                batch_count = 0
        
        # Commit del último batch si hay operaciones pendientes
        if batch_count > 0:
            batch.commit()
        
        return {
            "message": f"Se marcaron {updated_count} notificaciones como leídas",
            "updated_count": updated_count
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error actualizando notificaciones: {str(e)}"
        )


# -------------------- Contar notificaciones no leídas -------------------- #
@router.get("/unread/count")
def count_unread_notifications(
    current_user: dict = Depends(get_current_user)
):
    """
    Cuenta las notificaciones no leídas del usuario.
    """
    user_id = current_user.get("id")
    
    try:
        notifications_ref = db.collection("notifications").where("user_id", "==", user_id).where("is_read", "==", False)
        
        # Contar documentos (puede ser costoso para grandes colecciones)
        count = 0
        for _ in notifications_ref.stream():
            count += 1
        
        return {
            "user_id": user_id,
            "unread_count": count,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error contando notificaciones: {str(e)}"
        )


# -------------------- Eliminar notificación -------------------- #
@router.delete("/{notification_id}")
def delete_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Elimina una notificación.
    El usuario solo puede eliminar sus propias notificaciones.
    """
    notification_ref = db.collection("notifications").document(notification_id)
    notification_doc = notification_ref.get()
    
    if not notification_doc.exists:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    
    notification_data = notification_doc.to_dict()
    
    # Verificar permisos
    if not can_view_notification(current_user, notification_data):
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para eliminar esta notificación"
        )
    
    # Eliminar notificación
    notification_ref.delete()
    
    return {"message": "Notificación eliminada correctamente"}


# -------------------- Eliminar todas las notificaciones -------------------- #
@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_notifications(
    current_user: dict = Depends(get_current_user)
):
    """
    Elimina todas las notificaciones del usuario.
    Use with caution.
    """
    user_id = current_user.get("id")
    
    try:
        # Buscar todas las notificaciones del usuario
        notifications_ref = db.collection("notifications").where("user_id", "==", user_id)
        
        # Usar batch para eliminar en lote
        batch = db.batch()
        batch_count = 0
        deleted_count = 0
        
        for doc in notifications_ref.stream():
            notification_ref = db.collection("notifications").document(doc.id)
            batch.delete(notification_ref)
            batch_count += 1
            deleted_count += 1
            
            if batch_count >= 500:
                batch.commit()
                batch = db.batch()
                batch_count = 0
        
        if batch_count > 0:
            batch.commit()
        
        # No retornar contenido (204 No Content)
        return None
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error eliminando notificaciones: {str(e)}"
        )
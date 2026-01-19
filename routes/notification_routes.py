# notification_routes.py
from fastapi import APIRouter, HTTPException, Depends, Query, status
from typing import List, Optional
from datetime import datetime

from services.firebase_client import db
from models.notification import NotificationPublic
from models.enums import UserRole, NotificationType
from routes.auth_routes import get_current_user

# Configuración del router
router = APIRouter(tags=["Notifications"])

# Funciones auxiliares para manejo de notificaciones
def is_admin(current_user: dict) -> bool:
    return current_user.get("role") == UserRole.ADMIN

def can_view_notification(current_user: dict, notification_data: dict) -> bool:
    user_id = current_user.get("id")
    notification_user_id = notification_data.get("user_id")
    
    return user_id == notification_user_id

# Endpoint para listar notificaciones del usuario autenticado con filtros opcionales
@router.get("/", response_model=List[NotificationPublic])
def list_notifications(
    notification_type: Optional[NotificationType] = Query(None),
    is_read: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user)
):

    user_id = current_user.get("id")
    
    # Construcción de consulta base filtrada por usuario
    notifications_ref = db.collection("notifications").where("user_id", "==", user_id)
    
    # Aplicación de filtros opcionales por tipo y estado de lectura
    if notification_type:
        notifications_ref = notifications_ref.where("notification_type", "==", notification_type.value)
    
    if is_read is not None:
        notifications_ref = notifications_ref.where("is_read", "==", is_read)
    
    # Obtención de notificaciones con manejo de paginación
    notifications = []
    try:
        query = notifications_ref.order_by("created_at", direction="DESCENDING")
        
        if offset > 0:
            offset_query = query.limit(offset)
            offset_docs = list(offset_query.stream())
            if len(offset_docs) >= offset:
                last_doc = offset_docs[-1]
                query = query.start_after(last_doc)
        
        docs = query.limit(limit).stream()
        
        for doc in docs:
            notification_data = doc.to_dict()
            notification_data["id"] = doc.id
            
            if hasattr(notification_data.get("created_at"), 'timestamp'):
                notification_data["created_at"] = notification_data["created_at"].timestamp()
            
            notifications.append(NotificationPublic(**notification_data))
            
    except Exception as e:
        print(f"Error consultando notificaciones: {e}")
        # Consulta de respaldo para casos de error en consultas complejas
        notifications_ref = db.collection("notifications").where("user_id", "==", user_id)
        docs = notifications_ref.stream()
        notifications = []
        for doc in docs:
            notification_data = doc.to_dict()
            notification_data["id"] = doc.id
            if hasattr(notification_data.get("created_at"), 'timestamp'):
                notification_data["created_at"] = notification_data["created_at"].timestamp()
            notifications.append(NotificationPublic(**notification_data))
        
        notifications.sort(key=lambda x: x.created_at, reverse=True)
        notifications = notifications[offset:offset + limit]
    
    return notifications

# Endpoint para obtener una notificación específica por su ID
@router.get("/{notification_id}", response_model=NotificationPublic)
def get_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user)
):

    # Obtención del documento de notificación desde Firestore
    notification_doc = db.collection("notifications").document(notification_id).get()
    
    if not notification_doc.exists:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    
    notification_data = notification_doc.to_dict()
    notification_data["id"] = notification_id
    
    # Validación de permisos de visualización del usuario actual
    if not can_view_notification(current_user, notification_data):
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para ver esta notificación"
        )
    
    # Conversión de timestamp de Firestore a formato datetime estándar
    if hasattr(notification_data.get("created_at"), 'timestamp'):
        notification_data["created_at"] = notification_data["created_at"].timestamp()
    
    return NotificationPublic(**notification_data)


# Endpoint para marcar una notificación específica como leída
@router.patch("/{notification_id}/read", response_model=NotificationPublic)
def mark_as_read(
    notification_id: str,
    current_user: dict = Depends(get_current_user)
):

    notification_ref = db.collection("notifications").document(notification_id)
    notification_doc = notification_ref.get()
    
    if not notification_doc.exists:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    
    notification_data = notification_doc.to_dict()
    
    # Validación de permisos de modificación de la notificación
    if not can_view_notification(current_user, notification_data):
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para modificar esta notificación"
        )
    
    # Verificación del estado actual de lectura de la notificación
    if notification_data.get("is_read", False):
        notification_data["id"] = notification_id
        if hasattr(notification_data.get("created_at"), 'timestamp'):
            notification_data["created_at"] = notification_data["created_at"].timestamp()
        return NotificationPublic(**notification_data)
    
    # Actualización del estado de lectura en Firestore
    update_time = datetime.utcnow()
    notification_ref.update({
        "is_read": True,
        "updated_at": update_time
    })
    
    # Obtención de la notificación actualizada para respuesta
    updated_doc = notification_ref.get()
    updated_data = updated_doc.to_dict()
    updated_data["id"] = notification_id
    
    if hasattr(updated_data.get("created_at"), 'timestamp'):
        updated_data["created_at"] = updated_data["created_at"].timestamp()
    
    return NotificationPublic(**updated_data)


# Endpoint para marcar todas las notificaciones no leídas del usuario como leídas
@router.post("/mark-all-read")
def mark_all_as_read(
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user.get("id")
    
    try:
        # Consulta para obtener todas las notificaciones no leídas del usuario
        notifications_ref = db.collection("notifications").where("user_id", "==", user_id).where("is_read", "==", False)
        
        update_time = datetime.utcnow()
        updated_count = 0
        
        # Uso de operaciones batch para actualizaciones masivas eficientes
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
            
            # Manejo del límite de Firestore de 500 operaciones por batch
            if batch_count >= 500:
                batch.commit()
                batch = db.batch()
                batch_count = 0
        
        # Ejecución del batch final si contiene operaciones pendientes
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
    

# Endpoint para contar el número de notificaciones no leídas del usuario autenticado
@router.get("/unread/count")
def count_unread_notifications(
    current_user: dict = Depends(get_current_user)
):

    user_id = current_user.get("id")
    
    try:
        # Consulta para notificaciones no leídas del usuario actual
        notifications_ref = db.collection("notifications").where("user_id", "==", user_id).where("is_read", "==", False)
        
        # Conteo iterativo de documentos en la consulta resultante
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


# Endpoint para eliminación de una notificación específica
@router.delete("/{notification_id}")
def delete_notification(
    notification_id: str,
    current_user: dict = Depends(get_current_user)
):
    notification_ref = db.collection("notifications").document(notification_id)
    notification_doc = notification_ref.get()
    
    if not notification_doc.exists:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    
    notification_data = notification_doc.to_dict()
    
    # Validación de permisos de eliminación basada en propiedad de la notificación
    if not can_view_notification(current_user, notification_data):
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para eliminar esta notificación"
        )
    
    # Eliminación del documento de notificación en Firestore
    notification_ref.delete()
    
    return {"message": "Notificación eliminada correctamente"}


# Endpoint para eliminación de todas las notificaciones del usuario autenticado
@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
def delete_all_notifications(
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user.get("id")
    
    try:
        # Consulta para obtener todas las notificaciones del usuario
        notifications_ref = db.collection("notifications").where("user_id", "==", user_id)
        
        # Uso de operaciones batch para eliminación masiva eficiente
        batch = db.batch()
        batch_count = 0
        deleted_count = 0
        
        for doc in notifications_ref.stream():
            notification_ref = db.collection("notifications").document(doc.id)
            batch.delete(notification_ref)
            batch_count += 1
            deleted_count += 1
            
            # Manejo del límite de 500 operaciones por batch en Firestore
            if batch_count >= 500:
                batch.commit()
                batch = db.batch()
                batch_count = 0
        
        # Ejecución del batch final si contiene operaciones pendientes
        if batch_count > 0:
            batch.commit()
        
        return None
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error eliminando notificaciones: {str(e)}"
        )
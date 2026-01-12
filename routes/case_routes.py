# case_routes.py
from fastapi import APIRouter, HTTPException, Depends, Query, status, Form, File, UploadFile
from typing import List, Optional
from datetime import datetime
import uuid

from services.firebase_client import db
from services.cloudinary_client import cloudinary
import cloudinary.uploader

from models.case_update import CaseUpdatePublic
from models.enums import UpdateType, ReportStatus, UserRole, NotificationType
from models.notification import NotificationCreate
from routes.auth_routes import get_current_user

router = APIRouter(tags=["Case Updates"])


# -------------------- Funciones auxiliares -------------------- #
def is_admin(current_user: dict) -> bool:
    return current_user.get("role") == UserRole.ADMIN

def is_encargado(current_user: dict) -> bool:
    return current_user.get("role") == UserRole.ENCARGADO

def is_reportante(current_user: dict) -> bool:
    return current_user.get("role") == UserRole.REPORTANTE

def create_notification(user_id: str, report_id: Optional[str], title: str, 
                       message: str, notification_type: NotificationType):
    """Crea una notificación en Firestore"""
    notification_data = NotificationCreate(
        user_id=user_id,
        report_id=report_id,
        title=title,
        message=message,
        notification_type=notification_type
    ).dict()
    
    # ESTAS 4 LÍNEAS FALTAN - AGREGAR DATA CON REPORT_ID
    if report_id:
        notification_data["data"] = {"report_id": report_id}
    else:
        notification_data["data"] = {}
    
    notification_data["id"] = str(uuid.uuid4())
    notification_data["created_at"] = datetime.utcnow()
    notification_data["is_read"] = False
    
    db.collection("notifications").document(notification_data["id"]).set(notification_data)

# -------------------- Crear actualización de caso -------------------- #
@router.post("/updates", response_model=CaseUpdatePublic, status_code=status.HTTP_201_CREATED)
async def create_case_update(
    report_id: str = Form(...),
    message: str = Form(..., min_length=5),
    update_type: UpdateType = Form(UpdateType.AVANCE),
    new_status: Optional[ReportStatus] = Form(None),
    images: List[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Crea una nueva actualización para un caso.
    - Encargado: Solo para reportes asignados a él
    - Admin: Para cualquier reporte
    - Reportante: NO puede crear actualizaciones
    """
    user_id = current_user.get("id")
    user_role = current_user.get("role")
    username = current_user.get("username", "unknown")
    
    # Verificar permisos: solo encargado o admin
    if not (is_encargado(current_user) or is_admin(current_user)):
        raise HTTPException(
            status_code=403, 
            detail="Solo encargados y administradores pueden crear actualizaciones"
        )
    
    # 1. Verificar que el reporte existe
    report_ref = db.collection("reports").document(report_id)
    report_doc = report_ref.get()
    
    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    
    report_data = report_doc.to_dict()
    assigned_to = report_data.get("assigned_to")
    reporter_uid = report_data.get("reporter_uid")
    current_report_status = report_data.get("status")
    
    # 2. Verificar que el usuario tiene permisos sobre este reporte
    if is_encargado(current_user) and assigned_to != user_id:
        raise HTTPException(
            status_code=403, 
            detail="Solo puedes crear actualizaciones para reportes asignados a ti"
        )
    
    # 3. Validar cambio de estado si se proporciona Y ES DIFERENTE al actual
    if new_status and new_status != current_report_status:
        # Solo permitir ciertas transiciones de estado
        valid_transitions = {
            ReportStatus.PENDIENTE: [ReportStatus.ASIGNADO],
            ReportStatus.ASIGNADO: [ReportStatus.EN_PROCESO, ReportStatus.PENDIENTE],
            ReportStatus.EN_PROCESO: [ReportStatus.RESUELTO, ReportStatus.ASIGNADO],
            ReportStatus.RESUELTO: [ReportStatus.CERRADO, ReportStatus.EN_PROCESO],
            ReportStatus.CERRADO: []
        }
        
        if current_report_status == ReportStatus.CERRADO:
            raise HTTPException(status_code=400, detail="Reporte ya está cerrado")
        
        if new_status not in valid_transitions.get(ReportStatus(current_report_status), []):
            raise HTTPException(
                status_code=400, 
                detail=f"Transición de estado inválida: {current_report_status} -> {new_status}"
            )
        
        # Actualizar estado del reporte
        update_time = datetime.utcnow()
        report_ref.update({
            "status": new_status.value,
            "updated_at": update_time
        })
    # Si new_status es el mismo que current_report_status, NO actualizar estado (pero sí crear avance)
    elif new_status and new_status == current_report_status:
        # Solo crear avance sin cambiar estado
        pass
    
    # 4. Subir imágenes a Cloudinary
    image_urls = []
    if images:
        for image in images:
            try:
                # Subir directamente a Cloudinary
                upload_result = cloudinary.uploader.upload(
                    image.file,
                    folder=f"comunimapp/case_updates/{username}",
                    public_id=f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{image.filename}",
                    overwrite=True
                )
                image_urls.append(upload_result["secure_url"])
            except Exception as e:
                raise HTTPException(
                    status_code=500, 
                    detail=f"Error subiendo imagen {image.filename}: {str(e)}"
                )
    
    # 5. Crear actualización
    update_id = str(uuid.uuid4())
    created_at = datetime.utcnow()
    
    update_data = {
        "id": update_id,
        "report_id": report_id,
        "encargado_id": user_id,
        "message": message,
        "update_type": update_type.value,
        "new_status": new_status.value if new_status else None,
        "images": image_urls if image_urls else None,
        "created_at": created_at
    }
    
    db.collection("case_updates").document(update_id).set(update_data)
    
    # 6. Crear notificación para el reportante
    if reporter_uid:
        # Determinar tipo de notificación basado en update_type
        notif_type = NotificationType.NUEVO_AVANCE
        if new_status == ReportStatus.CERRADO:
            notif_type = NotificationType.CIERRE_CASO
        elif update_type == UpdateType.CAMBIO_ESTADO:
            notif_type = NotificationType.CAMBIO_ESTADO
        
        create_notification(
            user_id=reporter_uid,
            report_id=report_id,
            title=f"Actualización del caso",
            message=f"Nueva actualización: {message[:100]}...",
            notification_type=notif_type
        )
    
    # 6b. Crear notificación para el ADMIN
    # Buscar todos los usuarios admin
    admin_users_ref = db.collection("users").where("role", "==", UserRole.ADMIN.value)
    
    for admin_doc in admin_users_ref.stream():
        admin_data = admin_doc.to_dict()
        admin_id = admin_data.get("id")
        
        if admin_id:  # Solo si el admin existe
            # Determinar tipo de notificación para admin
            admin_notif_type = NotificationType.NUEVO_AVANCE
            if new_status == ReportStatus.CERRADO:
                admin_notif_type = NotificationType.CIERRE_CASO
            elif update_type == UpdateType.CAMBIO_ESTADO:
                admin_notif_type = NotificationType.CAMBIO_ESTADO
            
            create_notification(
                user_id=admin_id,
                report_id=report_id,
                title=f"Actualización en reporte asignado",
                message=f"El encargado {username} actualizó el reporte: {message[:100]}...",
                notification_type=admin_notif_type
            )
    
    # 7. Preparar respuesta pública (ocultar encargado_id para mantener anonimato)
    response_data = {
        "message": message,
        "update_type": update_type,
        "new_status": new_status,
        "images": image_urls if image_urls else None,
        "created_at": created_at
    }
    
    return CaseUpdatePublic(**response_data)


# -------------------- Listar actualizaciones de un reporte -------------------- #
@router.get("/updates", response_model=List[CaseUpdatePublic])
def list_case_updates(
    report_id: str = Query(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Lista todas las actualizaciones de un reporte específico.
    - Reportante: Solo puede ver actualizaciones de sus propios reportes
    - Encargado: Solo puede ver actualizaciones de reportes asignados a él
    - Admin: Puede ver actualizaciones de cualquier reporte
    """
    user_id = current_user.get("id")
    user_role = current_user.get("role")
    
    # 1. Verificar que el reporte existe y obtener sus datos
    report_doc = db.collection("reports").document(report_id).get()
    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    
    report_data = report_doc.to_dict()
    assigned_to = report_data.get("assigned_to")
    reporter_uid = report_data.get("reporter_uid")
    
    # 2. Verificar permisos para ver este reporte
    can_view = False
    if user_role == UserRole.ADMIN:
        can_view = True
    elif user_role == UserRole.ENCARGADO and assigned_to == user_id:
        can_view = True
    elif user_role == UserRole.REPORTANTE and reporter_uid == user_id:
        can_view = True
    
    if not can_view:
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para ver las actualizaciones de este reporte"
        )
    
    # 3. Obtener actualizaciones
    updates_ref = db.collection("case_updates").where("report_id", "==", report_id)
    updates = []
    
    for doc in updates_ref.stream():
        update_data = doc.to_dict()
        
        # Preparar respuesta pública (ocultar encargado_id)
        update_public = {
            "message": update_data.get("message"),
            "update_type": UpdateType(update_data.get("update_type")),
            "new_status": ReportStatus(update_data.get("new_status")) if update_data.get("new_status") else None,
            "images": update_data.get("images"),
            "created_at": update_data.get("created_at")
        }
        
        updates.append(CaseUpdatePublic(**update_public))
    
    # Ordenar por fecha de creación (más reciente primero)
    updates.sort(key=lambda x: x.created_at, reverse=True)
    
    return updates


# -------------------- Obtener actualización específica -------------------- #
@router.get("/updates/{update_id}", response_model=CaseUpdatePublic)
def get_case_update(
    update_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Obtiene una actualización específica por ID.
    Mismos permisos que listar actualizaciones.
    """
    # 1. Obtener la actualización
    update_doc = db.collection("case_updates").document(update_id).get()
    if not update_doc.exists:
        raise HTTPException(status_code=404, detail="Actualización no encontrada")
    
    update_data = update_doc.to_dict()
    report_id = update_data.get("report_id")
    
    # 2. Verificar permisos a través del reporte asociado
    report_doc = db.collection("reports").document(report_id).get()
    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Reporte asociado no encontrado")
    
    report_data = report_doc.to_dict()
    user_id = current_user.get("id")
    user_role = current_user.get("role")
    assigned_to = report_data.get("assigned_to")
    reporter_uid = report_data.get("reporter_uid")
    
    # 3. Verificar permisos
    can_view = False
    if user_role == UserRole.ADMIN:
        can_view = True
    elif user_role == UserRole.ENCARGADO and assigned_to == user_id:
        can_view = True
    elif user_role == UserRole.REPORTANTE and reporter_uid == user_id:
        can_view = True
    
    if not can_view:
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para ver esta actualización"
        )
    
    # 4. Preparar respuesta pública
    response_data = {
        "message": update_data.get("message"),
        "update_type": UpdateType(update_data.get("update_type")),
        "new_status": ReportStatus(update_data.get("new_status")) if update_data.get("new_status") else None,
        "images": update_data.get("images"),
        "created_at": update_data.get("created_at")
    }
    
    return CaseUpdatePublic(**response_data)


# -------------------- Eliminar actualización -------------------- #
@router.delete("/updates/{update_id}")
def delete_case_update(
    update_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Elimina una actualización.
    - Admin: Puede eliminar cualquier actualización
    - Encargado: Solo puede eliminar sus propias actualizaciones
    - Reportante: NO puede eliminar actualizaciones
    """
    user_id = current_user.get("id")
    user_role = current_user.get("role")
    
    # 1. Obtener la actualización
    update_ref = db.collection("case_updates").document(update_id)
    update_doc = update_ref.get()
    
    if not update_doc.exists:
        raise HTTPException(status_code=404, detail="Actualización no encontrada")
    
    update_data = update_doc.to_dict()
    encargado_id = update_data.get("encargado_id")
    encargado_username = None
    
    # Obtener username del encargado para encontrar la carpeta correcta
    if encargado_id:
        encargado_doc = db.collection("users").document(encargado_id).get()
        if encargado_doc.exists:
            encargado_data = encargado_doc.to_dict()
            encargado_username = encargado_data.get("username", "unknown")
    
    # 2. Verificar permisos
    if user_role == UserRole.ADMIN:
        # Admin puede eliminar cualquier actualización
        pass
    elif user_role == UserRole.ENCARGADO and encargado_id == user_id:
        # Encargado solo puede eliminar sus propias actualizaciones
        pass
    else:
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para eliminar esta actualización"
        )
    
    # 3. Eliminar imágenes de Cloudinary si existen (AHORA PARA AMBOS ROLES)
    images = update_data.get("images")
    if images:
        for image_url in images:
            try:
                # Extraer public_id de la URL de Cloudinary
                url_parts = image_url.split("/")
                if "cloudinary.com" in image_url:
                    # Encontrar el índice después de "upload"
                    upload_index = url_parts.index("upload") if "upload" in url_parts else -1
                    if upload_index >= 0 and upload_index + 2 < len(url_parts):
                        # La estructura es: .../upload/v1234567/folder/public_id.jpg
                        version_folder = url_parts[upload_index + 1]
                        filename_parts = url_parts[upload_index + 2].split(".")
                        if len(filename_parts) >= 2:
                            public_id = filename_parts[0]
                            
                            # Determinar la carpeta basada en el username del encargado
                            if encargado_username:
                                folder = f"comunimapp/case_updates/{encargado_username}"
                                full_public_id = f"{folder}/{public_id}"
                            else:
                                # Fallback: intentar con el public_id completo
                                full_public_id = f"comunimapp/case_updates/{public_id}"
                            
                            # Intentar eliminar la imagen de Cloudinary
                            result = cloudinary.uploader.destroy(full_public_id)
                            
                            # También intentar sin folder por si está en root
                            if result.get("result") != "ok":
                                cloudinary.uploader.destroy(public_id)
                                
            except Exception as e:
                # Continuar incluso si falla la eliminación de Cloudinary
                print(f"Advertencia: Error eliminando imagen de Cloudinary ({image_url}): {e}")
    
    # 4. Eliminar de Firestore
    update_ref.delete()
    
    return {"message": "Actualización eliminada correctamente"}


# -------------------- Contar actualizaciones por reporte -------------------- #
@router.get("/updates/{report_id}/count")
def count_case_updates(
    report_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Cuenta el número de actualizaciones de un reporte.
    Mismos permisos que listar actualizaciones.
    """
    # Verificar permisos (usando la misma lógica que list_case_updates)
    report_doc = db.collection("reports").document(report_id).get()
    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    
    report_data = report_doc.to_dict()
    user_id = current_user.get("id")
    user_role = current_user.get("role")
    assigned_to = report_data.get("assigned_to")
    reporter_uid = report_data.get("reporter_uid")
    
    can_view = False
    if user_role == UserRole.ADMIN:
        can_view = True
    elif user_role == UserRole.ENCARGADO and assigned_to == user_id:
        can_view = True
    elif user_role == UserRole.REPORTANTE and reporter_uid == user_id:
        can_view = True
    
    if not can_view:
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para ver este reporte"
        )
    
    # Contar actualizaciones
    updates_ref = db.collection("case_updates").where("report_id", "==", report_id)
    count = 0
    for _ in updates_ref.stream():
        count += 1
    
    return {"report_id": report_id, "update_count": count}


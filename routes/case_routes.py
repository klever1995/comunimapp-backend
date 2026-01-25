# case_routes.py
from fastapi import APIRouter, HTTPException, Depends, Query, status, Form, File, UploadFile
from typing import List, Optional
from datetime import datetime
import uuid
import os

from services.firebase_client import db
from services.cloudinary_client import cloudinary
import cloudinary.uploader

from models.case_update import CaseUpdatePublic
from models.enums import UpdateType, ReportStatus, UserRole, NotificationType
from models.notification import NotificationCreate
from routes.auth_routes import get_current_user

# Configuración del router
router = APIRouter(tags=["Case Updates"])

# Funciones auxiliares para verificación de roles de usuario
def is_admin(current_user: dict) -> bool:
    return current_user.get("role") == UserRole.ADMIN

def is_encargado(current_user: dict) -> bool:
    return current_user.get("role") == UserRole.ENCARGADO

def is_reportante(current_user: dict) -> bool:
    return current_user.get("role") == UserRole.REPORTANTE

# Función para crear notificaciones en la base de datos Firestore
def create_notification(user_id: str, report_id: Optional[str], title: str, 
                       message: str, notification_type: NotificationType):
    notification_data = NotificationCreate(
        user_id=user_id,
        report_id=report_id,
        title=title,
        message=message,
        notification_type=notification_type
    ).dict()
    
    if report_id:
        notification_data["data"] = {"report_id": report_id}
    else:
        notification_data["data"] = {}
    
    notification_data["id"] = str(uuid.uuid4())
    notification_data["created_at"] = datetime.utcnow()
    notification_data["is_read"] = False
    
    db.collection("notifications").document(notification_data["id"]).set(notification_data)

# Endpoint para creación de actualizaciones en casos existentes
@router.post("/updates", response_model=CaseUpdatePublic, status_code=status.HTTP_201_CREATED)
async def create_case_update(
    report_id: str = Form(...),
    message: str = Form(..., min_length=5),
    update_type: UpdateType = Form(UpdateType.AVANCE),
    new_status: Optional[ReportStatus] = Form(None),
    images: List[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user)
):

    user_id = current_user.get("id")
    user_role = current_user.get("role")
    username = current_user.get("username", "unknown")
    
    # Verificación de permisos por rol de usuario
    if not (is_encargado(current_user) or is_admin(current_user)):
        raise HTTPException(
            status_code=403, 
            detail="Solo encargados y administradores pueden crear actualizaciones"
        )
    
    # Validación de existencia del reporte en Firestore
    report_ref = db.collection("reports").document(report_id)
    report_doc = report_ref.get()
    
    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    
    report_data = report_doc.to_dict()
    assigned_to = report_data.get("assigned_to")
    reporter_uid = report_data.get("reporter_uid")
    current_report_status = report_data.get("status")
    
    # Validación de permisos específicos sobre el reporte
    if is_encargado(current_user) and assigned_to != user_id:
        raise HTTPException(
            status_code=403, 
            detail="Solo puedes crear actualizaciones para reportes asignados a ti"
        )
    
    # Validación y actualización de estado del reporte si se proporciona uno nuevo
    if new_status and new_status != current_report_status:
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
        
        update_time = datetime.utcnow()
        report_ref.update({
            "status": new_status.value,
            "updated_at": update_time
        })
    elif new_status and new_status == current_report_status:
        pass
    
    # Procesamiento y validación de imágenes adjuntas
    image_urls = []
    if images:
        for image in images:
            try:
                allowed_extensions = {'.jpg', '.jpeg', '.png', '.gif'}
                file_extension = os.path.splitext(image.filename)[1].lower()
                if file_extension not in allowed_extensions:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Tipo de archivo no permitido: {image.filename}. Solo se aceptan JPG, PNG o GIF"
                    )
                
                MAX_FILE_SIZE = 5 * 1024 * 1024
                image.file.seek(0, 2)
                file_size = image.file.tell()
                image.file.seek(0)
                
                if file_size > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Imagen {image.filename} excede el tamaño máximo de 5MB"
                    )
                
                upload_result = cloudinary.uploader.upload(
                    image.file,
                    folder=f"comunimapp/case_updates/{username}",
                    public_id=f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{image.filename}",
                    overwrite=True
                )
                image_urls.append(upload_result["secure_url"])
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(
                    status_code=500, 
                    detail=f"Error subiendo imagen {image.filename}: {str(e)}"
                )
    
    # Creación del documento de actualización en Firestore
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
    
    # Envío de notificación push al reportante original del caso
    if reporter_uid:
        try:
            print(f"[DEBUG NOTIFICACIÓN AVANCE] Buscando token del reportante {reporter_uid}")
            
            reporter_doc = db.collection("users").document(reporter_uid).get()
            if reporter_doc.exists:
                reporter_data = reporter_doc.to_dict()
                reporter_token = reporter_data.get("fcm_token")
                
                if reporter_token:
                
                    print(f"[DEBUG NOTIFICACIÓN AVANCE] Token encontrado: {reporter_token[:20]}...")
                    
                    try:
                        from firebase_admin import messaging
                        
                        title = "📝 Nuevo avance en tu reporte"
                        if new_status == ReportStatus.CERRADO:
                            title = "✅ Caso cerrado"
                        elif update_type == UpdateType.CAMBIO_ESTADO:
                            title = "🔄 Cambio de estado"
                        
                        body = f"{username}: {message[:80]}..."
                        if len(message) > 80:
                            body += "..."
                        
                        message_obj = messaging.Message(
                            notification=messaging.Notification(
                                title=title,
                                body=body,
                            ),
                            token=reporter_token,
                            data={
                                "report_id": report_id,
                                "update_id": update_id,
                                "type": "nuevo_avance",
                                "update_type": update_type.value,
                                "new_status": new_status.value if new_status else "",
                                "encargado_name": username
                            }
                        )
                        
                        response = messaging.send(message_obj)
                        print(f"[DEBUG NOTIFICACIÓN AVANCE]  Push enviado al reportante. ID: {response}")
                        
                    except ImportError:
                        print("[ERROR] 'firebase-admin' no está instalado.")
                    except Exception as e:
                        print(f"[ERROR NOTIFICACIÓN AVANCE] Error enviando push: {str(e)}")
                else:
                    print(f"[DEBUG NOTIFICACIÓN AVANCE] Reportante {reporter_uid} no tiene token FCM registrado.")
            else:
                print(f"[DEBUG NOTIFICACIÓN AVANCE] Reportante {reporter_uid} no encontrado.")
                
        except Exception as e:
            print(f"[ERROR CRÍTICO NOTIFICACIÓN AVANCE] Falló todo el proceso: {str(e)}")
    
    # Creación de notificaciones en base de datos para el reportante
    if reporter_uid:
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
    
    # Creación de notificaciones para todos los administradores del sistema
    admin_users_ref = db.collection("users").where("role", "==", UserRole.ADMIN.value)
    
    for admin_doc in admin_users_ref.stream():
        admin_data = admin_doc.to_dict()
        admin_id = admin_data.get("id")
        
        if admin_id:
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
    
    # Preparación de respuesta pública para el cliente
    response_data = {
        "message": message,
        "update_type": update_type,
        "new_status": new_status,
        "images": image_urls if image_urls else None,
        "created_at": created_at
    }
    
    return CaseUpdatePublic(**response_data)

# Endpoint para listar todas las actualizaciones de un reporte específico
@router.get("/updates", response_model=List[CaseUpdatePublic])
def list_case_updates(
    report_id: str = Query(...),
    current_user: dict = Depends(get_current_user)
):

    user_id = current_user.get("id")
    user_role = current_user.get("role")
    
    # Verificación de existencia del reporte en Firestore
    report_doc = db.collection("reports").document(report_id).get()
    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    
    report_data = report_doc.to_dict()
    assigned_to = report_data.get("assigned_to")
    reporter_uid = report_data.get("reporter_uid")
    
    # Validación de permisos según rol del usuario
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
    
    # Obtención de actualizaciones desde la colección case_updates
    updates_ref = db.collection("case_updates").where("report_id", "==", report_id)
    updates = []
    
    for doc in updates_ref.stream():
        update_data = doc.to_dict()
        
        update_public = {
            "message": update_data.get("message"),
            "update_type": UpdateType(update_data.get("update_type")),
            "new_status": ReportStatus(update_data.get("new_status")) if update_data.get("new_status") else None,
            "images": update_data.get("images"),
            "created_at": update_data.get("created_at")
        }
        
        updates.append(CaseUpdatePublic(**update_public))
    
    # Ordenamiento cronológico inverso (más reciente primero)
    updates.sort(key=lambda x: x.created_at, reverse=True)
    
    return updates

# Endpoint para obtener una actualización específica de caso por su ID
@router.get("/updates/{update_id}", response_model=CaseUpdatePublic)
def get_case_update(
    update_id: str,
    current_user: dict = Depends(get_current_user)
):
    # Obtención del documento de actualización desde Firestore
    update_doc = db.collection("case_updates").document(update_id).get()
    if not update_doc.exists:
        raise HTTPException(status_code=404, detail="Actualización no encontrada")
    
    update_data = update_doc.to_dict()
    report_id = update_data.get("report_id")
    
    # Verificación del reporte asociado a la actualización
    report_doc = db.collection("reports").document(report_id).get()
    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Reporte asociado no encontrado")
    
    report_data = report_doc.to_dict()
    user_id = current_user.get("id")
    user_role = current_user.get("role")
    assigned_to = report_data.get("assigned_to")
    reporter_uid = report_data.get("reporter_uid")
    
    # Validación de permisos de visualización según rol del usuario
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
    
    # Preparación de datos para respuesta pública
    response_data = {
        "message": update_data.get("message"),
        "update_type": UpdateType(update_data.get("update_type")),
        "new_status": ReportStatus(update_data.get("new_status")) if update_data.get("new_status") else None,
        "images": update_data.get("images"),
        "created_at": update_data.get("created_at")
    }
    
    return CaseUpdatePublic(**response_data)


# Endpoint para eliminación de actualizaciones de casos existentes
@router.delete("/updates/{update_id}")
def delete_case_update(
    update_id: str,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user.get("id")
    user_role = current_user.get("role")
    
    # Obtención del documento de actualización a eliminar
    update_ref = db.collection("case_updates").document(update_id)
    update_doc = update_ref.get()
    
    if not update_doc.exists:
        raise HTTPException(status_code=404, detail="Actualización no encontrada")
    
    update_data = update_doc.to_dict()
    encargado_id = update_data.get("encargado_id")
    encargado_username = None
    
    # Obtención del nombre de usuario del encargado para estructura de carpetas
    if encargado_id:
        encargado_doc = db.collection("users").document(encargado_id).get()
        if encargado_doc.exists:
            encargado_data = encargado_doc.to_dict()
            encargado_username = encargado_data.get("username", "unknown")
    
    # Validación de permisos de eliminación según rol del usuario
    if user_role == UserRole.ADMIN:
        pass
    elif user_role == UserRole.ENCARGADO and encargado_id == user_id:
        pass
    else:
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para eliminar esta actualización"
        )
    
    # Eliminación de imágenes asociadas en Cloudinary si existen
    images = update_data.get("images")
    if images:
        for image_url in images:
            try:
                url_parts = image_url.split("/")
                if "cloudinary.com" in image_url:
                    upload_index = url_parts.index("upload") if "upload" in url_parts else -1
                    if upload_index >= 0 and upload_index + 2 < len(url_parts):
                        version_folder = url_parts[upload_index + 1]
                        filename_parts = url_parts[upload_index + 2].split(".")
                        if len(filename_parts) >= 2:
                            public_id = filename_parts[0]
                            
                            if encargado_username:
                                folder = f"comunimapp/case_updates/{encargado_username}"
                                full_public_id = f"{folder}/{public_id}"
                            else:
                                full_public_id = f"comunimapp/case_updates/{public_id}"
                            
                            result = cloudinary.uploader.destroy(full_public_id)
                            
                            if result.get("result") != "ok":
                                cloudinary.uploader.destroy(public_id)
                                
            except Exception as e:
                print(f"Advertencia: Error eliminando imagen de Cloudinary ({image_url}): {e}")
    
    # Eliminación del documento de actualización en Firestore
    update_ref.delete()
    
    return {"message": "Actualización eliminada correctamente"}


# Endpoint para contar el número de actualizaciones asociadas a un reporte específico
@router.get("/updates/{report_id}/count")
def count_case_updates(
    report_id: str,
    current_user: dict = Depends(get_current_user)
):

    # Validación de existencia del reporte en Firestore
    report_doc = db.collection("reports").document(report_id).get()
    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    
    report_data = report_doc.to_dict()
    user_id = current_user.get("id")
    user_role = current_user.get("role")
    assigned_to = report_data.get("assigned_to")
    reporter_uid = report_data.get("reporter_uid")
    
    # Verificación de permisos de visualización según rol del usuario
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
    
    # Conteo de documentos en la colección case_updates para el reporte específico
    updates_ref = db.collection("case_updates").where("report_id", "==", report_id)
    count = 0
    for _ in updates_ref.stream():
        count += 1
    
    return {"report_id": report_id, "update_count": count}
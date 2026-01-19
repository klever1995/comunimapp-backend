# report_routes.py
from fastapi import APIRouter, HTTPException, Depends, Query, status, Form, File, UploadFile
from typing import List, Optional
from datetime import datetime
import uuid
import os

from services.cloudinary_client import cloudinary
import cloudinary.uploader
from services.firebase_client import db
from models.report import ReportPublic, ReportLocation
from models.enums import ReportStatus, ReportPriority, UserRole, NotificationType
from models.notification import NotificationCreate
from routes.auth_routes import get_current_user

# Configuración del router
router = APIRouter(tags=["Reports"])

# Funciones auxiliares para verificación de roles de usuario en reportes
def is_admin(current_user: dict) -> bool:
    return current_user.get("role") == UserRole.ADMIN

def is_encargado(current_user: dict) -> bool:
    return current_user.get("role") == UserRole.ENCARGADO

def is_reportante(current_user: dict) -> bool:
    return current_user.get("role") == UserRole.REPORTANTE

# Función para creación de notificaciones en el sistema de reportes
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


# Endpoint para creación de nuevos reportes por parte de usuarios reportantes
@router.post("/", response_model=ReportPublic, status_code=status.HTTP_201_CREATED)
async def create_report(
    description: str = Form(..., min_length=10),
    latitude: float = Form(...),
    longitude: float = Form(...),
    address: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    is_anonymous: bool = Form(False),
    priority: ReportPriority = Form(ReportPriority.MEDIA),
    images: List[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user)
):
    if not is_reportante(current_user):
        raise HTTPException(
            status_code=403, 
            detail="Solo los reportantes pueden crear reportes"
        )
    
    user_id = current_user.get("id")
    username = current_user.get("username", "unknown")
    
    # Procesamiento y validación de imágenes adjuntas al reporte
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
                    folder=f"comunimapp/reports/{username}",
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
    
    location = ReportLocation(
        latitude=latitude,
        longitude=longitude,
        address=address,
        city=city
    )
    
    # Generación de identificador único y timestamp para el reporte
    report_id = str(uuid.uuid4())
    created_at = datetime.utcnow()
    
    # Preparación del documento de reporte para almacenamiento en Firestore
    report_dict = {
        "id": report_id,
        "description": description,
        "location": location.dict(),
        "images": image_urls if image_urls else None,
        "reporter_uid": user_id,
        "is_anonymous_public": is_anonymous,
        "priority": priority.value,
        "status": ReportStatus.PENDIENTE.value,
        "created_at": created_at,
        "updated_at": None,
        "assigned_to": None
    }
    
    db.collection("reports").document(report_id).set(report_dict)

    # Envío de notificaciones push a todos los administradores del sistema
    try:
        print(f"[DEBUG NOTIFICACIÓN ADMIN] Buscando admins para notificar sobre reporte {report_id}")
        
        admins_ref = db.collection("users").where("role", "==", UserRole.ADMIN.value).stream()
        admin_count = 0
        success_count = 0
        
        for admin_doc in admins_ref:
            admin_count += 1
            admin_data = admin_doc.to_dict()
            admin_id = admin_data.get("id")
            admin_tokens = admin_data.get("fcm_tokens", [])
            
            if admin_tokens:
                admin_token = admin_tokens[0]
                print(f"[DEBUG NOTIFICACIÓN ADMIN] Enviando a admin {admin_id}, token: {admin_token[:20]}...")
                
                try:
                    from firebase_admin import messaging
                    
                    message = messaging.Message(
                        notification=messaging.Notification(
                            title="📋 Nuevo reporte pendiente",
                            body=f"Un nuevo reporte requiere asignación: '{description[:40]}...'",
                        ),
                        token=admin_token,
                        data={
                            "report_id": report_id,
                            "type": "nuevo_reporte_admin"
                        }
                    )
                    
                    response = messaging.send(message)
                    print(f"[DEBUG NOTIFICACIÓN ADMIN] Push enviado a admin {admin_id}. ID: {response}")
                    success_count += 1
                    
                except Exception as e:
                    print(f"[ERROR NOTIFICACIÓN ADMIN] Error enviando a admin {admin_id}: {str(e)}")
            else:
                print(f"[DEBUG NOTIFICACIÓN ADMIN] Admin {admin_id} no tiene token FCM registrado.")
        
        print(f"[DEBUG NOTIFICACIÓN ADMIN] Resumen: {success_count}/{admin_count} admins notificados exitosamente.")
        
    except Exception as e:
        print(f"[ERROR CRÍTICO NOTIFICACIÓN ADMIN] Falló el proceso de notificación a admins: {str(e)}")
    
    # Creación de notificaciones en base de datos para todos los administradores
    admins_ref_db = db.collection("users").where("role", "==", UserRole.ADMIN.value).stream()
    for admin_doc in admins_ref_db:
        admin_data = admin_doc.to_dict()
        create_notification(
            user_id=admin_data.get("id"),
            report_id=report_id,
            title="Nuevo reporte pendiente",
            message=f"Hay un nuevo reporte pendiente de asignación: {description[:50]}...",
            notification_type=NotificationType.NUEVO_REPORTE
        )
    
    # Preparación de respuesta pública para el cliente
    response_data = {
        "id": report_id,
        "description": description,
        "location": location.dict(),
        "images": image_urls if image_urls else None,
        "priority": priority,
        "status": ReportStatus.PENDIENTE,
        "created_at": created_at,
        "updated_at": None,
        "assigned_to": None
    }
    
    response_data["reporter_uid"] = None if is_anonymous else user_id
    
    return ReportPublic(**response_data)

# Endpoint para listar reportes con sistema de filtros por rol y estado
@router.get("/", response_model=List[ReportPublic])
def list_reports(
    status: Optional[ReportStatus] = Query(None),
    priority: Optional[ReportPriority] = Query(None),
    assigned_to_me: Optional[bool] = Query(None, description="Filtrar solo reportes asignados a mí"),
    current_user: dict = Depends(get_current_user)
):

    user_id = current_user.get("id")
    user_role = current_user.get("role")
    
    reports_ref = db.collection("reports")
    
    # Aplicación de filtros comunes por estado y prioridad
    if status:
        reports_ref = reports_ref.where("status", "==", status.value)
    if priority:
        reports_ref = reports_ref.where("priority", "==", priority.value)
    
    # Filtrado de reportes según el rol del usuario autenticado
    if user_role == UserRole.ADMIN:
        pass
    elif user_role == UserRole.ENCARGADO:
        if assigned_to_me:
            reports_ref = reports_ref.where("assigned_to", "==", user_id)
        else:
            reports_ref = reports_ref.where("assigned_to", "==", user_id)
    elif user_role == UserRole.REPORTANTE:
        reports_ref = reports_ref.where("reporter_uid", "==", user_id)
    else:
        raise HTTPException(status_code=403, detail="Rol no autorizado")
    
    reports = []
    for doc in reports_ref.stream():
        report_data = doc.to_dict()
        report_id = report_data.get("id")
        
        # Preparación de datos públicos del reporte para respuesta
        response_data = {
            "id": report_id,
            "description": report_data.get("description"),
            "location": report_data.get("location"),
            "images": report_data.get("images"),
            "priority": report_data.get("priority"),
            "status": report_data.get("status"),
            "created_at": report_data.get("created_at"),
            "updated_at": report_data.get("updated_at"),
            "assigned_to": report_data.get("assigned_to")
        }
        
        # Lógica de anonimato para visibilidad del ID del reportante
        is_anonymous = report_data.get("is_anonymous_public", False)
        can_see_reporter = (
            user_role == UserRole.ADMIN or
            user_id == report_data.get("reporter_uid")
        )
        
        if can_see_reporter or not is_anonymous:
            response_data["reporter_uid"] = report_data.get("reporter_uid")
        else:
            response_data["reporter_uid"] = None
        
        reports.append(ReportPublic(**response_data))
    
    return reports


# Endpoint para obtener un reporte específico por su identificador único
@router.get("/{report_id}", response_model=ReportPublic)
def get_report(
    report_id: str,
    current_user: dict = Depends(get_current_user)
):

    doc = db.collection("reports").document(report_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    
    report_data = doc.to_dict()
    user_id = current_user.get("id")
    user_role = current_user.get("role")
    
    # Validación de permisos de acceso basada en rol y asignación
    reporter_uid = report_data.get("reporter_uid")
    assigned_to = report_data.get("assigned_to")
    
    can_access = False
    if user_role == UserRole.ADMIN:
        can_access = True
    elif user_role == UserRole.ENCARGADO and assigned_to == user_id:
        can_access = True
    elif user_role == UserRole.REPORTANTE and reporter_uid == user_id:
        can_access = True
    
    if not can_access:
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para ver este reporte"
        )
    
    # Preparación de datos del reporte para respuesta al cliente
    response_data = {
        "id": report_id,
        "description": report_data.get("description"),
        "location": report_data.get("location"),
        "images": report_data.get("images"),
        "priority": report_data.get("priority"),
        "status": report_data.get("status"),
        "created_at": report_data.get("created_at"),
        "updated_at": report_data.get("updated_at"),
        "assigned_to": report_data.get("assigned_to")
    }
    
    # Manejo de anonimato para exposición del ID del reportante
    is_anonymous = report_data.get("is_anonymous_public", False)
    can_see_reporter = (
        user_role == UserRole.ADMIN or
        user_id == reporter_uid
    )
    
    if can_see_reporter or not is_anonymous:
        response_data["reporter_uid"] = reporter_uid
    else:
        response_data["reporter_uid"] = None
    
    return ReportPublic(**response_data)


# Endpoint para asignar reportes a encargados específicos
@router.put("/{report_id}/assign", response_model=ReportPublic)
def assign_report(
    report_id: str,
    encargado_id: str = Query(..., description="ID del encargado a asignar"),
    current_user: dict = Depends(get_current_user)
):

    if not is_admin(current_user):
        raise HTTPException(
            status_code=403, 
            detail="Solo administradores pueden asignar reportes"
        )
    
    # Verificación de existencia del reporte en Firestore
    report_ref = db.collection("reports").document(report_id)
    report_doc = report_ref.get()
    
    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    
    report_data = report_doc.to_dict()
    
    # Validación del estado actual del reporte (debe estar pendiente)
    if report_data.get("status") != ReportStatus.PENDIENTE:
        raise HTTPException(
            status_code=400, 
            detail=f"El reporte ya está en estado: {report_data.get('status')}"
        )
    
    # Verificación del encargado y validación de su rol
    encargado_doc = db.collection("users").document(encargado_id).get()
    if not encargado_doc.exists:
        raise HTTPException(status_code=404, detail="Encargado no encontrado")
    
    encargado_data = encargado_doc.to_dict()
    if encargado_data.get("role") != UserRole.ENCARGADO:
        raise HTTPException(status_code=400, detail="El usuario no es un encargado")
    
    # Actualización del estado y asignación del reporte en Firestore
    update_time = datetime.utcnow()
    report_ref.update({
        "assigned_to": encargado_id,
        "status": ReportStatus.ASIGNADO,
        "updated_at": update_time
    })
    
    # Obtención del reporte actualizado para operaciones posteriores
    updated_doc = report_ref.get()
    updated_data = updated_doc.to_dict()
    
    # Creación de notificaciones en base de datos para ambas partes
    reporter_uid = updated_data.get("reporter_uid")
    
    create_notification(
        user_id=reporter_uid,
        report_id=report_id,
        title="Reporte asignado",
        message=f"Tu reporte ha sido asignado a un encargado",
        notification_type=NotificationType.ASIGNACION_CASO
    )
    
    create_notification(
        user_id=encargado_id,
        report_id=report_id,
        title="Nuevo reporte asignado",
        message="Se te ha asignado un nuevo reporte",
        notification_type=NotificationType.ASIGNACION_CASO
    )

    # Envío de notificación push al encargado asignado
    try:
        print(f"[DEBUG NOTIFICACIÓN ASIGNACIÓN] Buscando token del encargado {encargado_id}")
        
        encargado_tokens = encargado_data.get("fcm_tokens", [])
        
        if encargado_tokens:
            encargado_token = encargado_tokens[0]
            print(f"[DEBUG NOTIFICACIÓN ASIGNACIÓN] Token encontrado: {encargado_token[:20]}...")
            
            try:
                from firebase_admin import messaging
                
                message = messaging.Message(
                    notification=messaging.Notification(
                        title="📋 Nuevo reporte asignado",
                        body=f"Se te ha asignado el reporte: '{report_data.get('description', '')[:40]}...'",
                    ),
                    token=encargado_token,
                    data={
                        "report_id": report_id,
                        "type": "reporte_asignado",
                        "assigner_id": current_user.get("id"),
                        "priority": report_data.get("priority", "media")
                    }
                )
                
                response = messaging.send(message)
                print(f"[DEBUG NOTIFICACIÓN ASIGNACIÓN] Push enviado al encargado. ID: {response}")
                
            except ImportError:
                print("[ERROR] 'firebase-admin' no está instalado.")
            except Exception as e:
                print(f"[ERROR NOTIFICACIÓN ASIGNACIÓN] Error enviando push: {str(e)}")
        else:
            print(f"[DEBUG NOTIFICACIÓN ASIGNACIÓN] Encargado {encargado_id} no tiene token FCM registrado.")
            
    except Exception as e:
        print(f"[ERROR CRÍTICO NOTIFICACIÓN ASIGNACIÓN] Falló todo el proceso: {str(e)}")

    # Envío de notificación push al reportante original
    try:
        print(f"[DEBUG NOTIFICACIÓN ASIGNACIÓN] Buscando token del reportante {reporter_uid}")
        
        reporter_doc = db.collection("users").document(reporter_uid).get()
        if reporter_doc.exists:
            reporter_data = reporter_doc.to_dict()
            reporter_tokens = reporter_data.get("fcm_tokens", [])
            
            if reporter_tokens:
                reporter_token = reporter_tokens[0]
                print(f"[DEBUG NOTIFICACIÓN ASIGNACIÓN] Token encontrado para reportante: {reporter_token[:20]}...")
                
                try:
                    from firebase_admin import messaging
                    
                    message = messaging.Message(
                        notification=messaging.Notification(
                            title="✅ Reporte asignado",
                            body=f"Tu reporte ha sido asignado a un encargado para su atención",
                        ),
                        token=reporter_token,
                        data={
                            "report_id": report_id,
                            "type": "reporte_asignado_reporter",
                            "assigned_to": encargado_id,
                            "priority": report_data.get("priority", "media")
                        }
                    )
                    
                    response = messaging.send(message)
                    print(f"[DEBUG NOTIFICACIÓN ASIGNACIÓN] Push enviado al reportante. ID: {response}")
                    
                except ImportError:
                    print("[ERROR] 'firebase-admin' no está instalado.")
                except Exception as e:
                    print(f"[ERROR NOTIFICACIÓN ASIGNACIÓN] Error enviando push al reportante: {str(e)}")
            else:
                print(f"[DEBUG NOTIFICACIÓN ASIGNACIÓN] Reportante {reporter_uid} no tiene token FCM registrado.")
        else:
            print(f"[DEBUG NOTIFICACIÓN ASIGNACIÓN] Reportante {reporter_uid} no encontrado.")
            
    except Exception as e:
        print(f"[ERROR CRÍTICO NOTIFICACIÓN ASIGNACIÓN] Falló proceso de notificación al reportante: {str(e)}")

    # Preparación de respuesta con datos actualizados del reporte
    response_data = {
        "id": report_id,
        "description": updated_data.get("description"),
        "location": updated_data.get("location"),
        "images": updated_data.get("images"),
        "priority": updated_data.get("priority"),
        "status": updated_data.get("status"),
        "created_at": updated_data.get("created_at"),
        "updated_at": updated_data.get("updated_at"),
        "assigned_to": encargado_id,
        "reporter_uid": reporter_uid
    }
    
    return ReportPublic(**response_data)

# Endpoint para eliminación de reportes del sistema
@router.delete("/{report_id}")
def delete_report(
    report_id: str,
    current_user: dict = Depends(get_current_user)
):

    user_id = current_user.get("id")
    user_role = current_user.get("role")
    
    report_ref = db.collection("reports").document(report_id)
    report_doc = report_ref.get()
    
    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    
    report_data = report_doc.to_dict()
    reporter_uid = report_data.get("reporter_uid")
    report_status = report_data.get("status")
    
    # Validación de permisos de eliminación según rol del usuario
    if user_role == UserRole.ADMIN:
        pass
    elif user_role == UserRole.REPORTANTE:
        if reporter_uid != user_id:
            raise HTTPException(
                status_code=403, 
                detail="Solo puedes eliminar tus propios reportes"
            )
        if report_status != ReportStatus.PENDIENTE:
            raise HTTPException(
                status_code=400, 
                detail="Solo puedes eliminar reportes pendientes"
            )
    else:
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para eliminar reportes"
        )
    
    # Eliminación del documento de reporte en Firestore
    report_ref.delete()
    
    # Eliminación de notificaciones asociadas al reporte eliminado
    notifications_ref = db.collection("notifications").where("report_id", "==", report_id).stream()
    for notif_doc in notifications_ref:
        notif_doc.reference.delete()
    
    return {"message": "Reporte eliminado correctamente"}

# Endpoint para actualización del estado de reportes existentes
@router.patch("/{report_id}/status", response_model=ReportPublic)
def update_report_status(
    report_id: str,
    new_status: ReportStatus = Query(...),
    current_user: dict = Depends(get_current_user)
):

    user_id = current_user.get("id")
    user_role = current_user.get("role")
    
    report_ref = db.collection("reports").document(report_id)
    report_doc = report_ref.get()
    
    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    
    report_data = report_doc.to_dict()
    assigned_to = report_data.get("assigned_to")
    
    # Verificación de permisos por rol del usuario
    if user_role == UserRole.ADMIN:
        pass
    elif user_role == UserRole.ENCARGADO:
        if assigned_to != user_id:
            raise HTTPException(
                status_code=403, 
                detail="Solo puedes cambiar estado de reportes asignados a ti"
            )
    else:
        raise HTTPException(
            status_code=403, 
            detail="No tienes permisos para cambiar el estado"
        )
    
    # Validación de transiciones de estado permitidas en el flujo de trabajo
    current_status = report_data.get("status")
    
    valid_transitions = {
        ReportStatus.PENDIENTE: [ReportStatus.ASIGNADO],
        ReportStatus.ASIGNADO: [ReportStatus.EN_PROCESO, ReportStatus.PENDIENTE],
        ReportStatus.EN_PROCESO: [ReportStatus.RESUELTO, ReportStatus.ASIGNADO],
        ReportStatus.RESUELTO: [ReportStatus.CERRADO, ReportStatus.EN_PROCESO],
        ReportStatus.CERRADO: []
    }
    
    if current_status == ReportStatus.CERRADO:
        raise HTTPException(status_code=400, detail="Reporte ya está cerrado")
    
    if new_status not in valid_transitions.get(current_status, []):
        raise HTTPException(
            status_code=400, 
            detail=f"Transición de estado inválida: {current_status} -> {new_status}"
        )
    
    # Actualización del estado del reporte en Firestore
    update_time = datetime.utcnow()
    report_ref.update({
        "status": new_status.value,
        "updated_at": update_time
    })
    
    # Notificación al reportante cuando el caso se cierra
    updated_doc = report_ref.get()
    updated_data = updated_doc.to_dict()
    
    if new_status == ReportStatus.CERRADO:
        reporter_uid = updated_data.get("reporter_uid")
        
        create_notification(
            user_id=reporter_uid,
            report_id=report_id,
            title="Reporte cerrado",
            message="Tu reporte ha sido cerrado",
            notification_type=NotificationType.CIERRE_CASO
        )
    
    # Preparación de respuesta con datos actualizados
    response_data = {
        "id": report_id,
        "description": updated_data.get("description"),
        "location": updated_data.get("location"),
        "images": updated_data.get("images"),
        "priority": updated_data.get("priority"),
        "status": new_status,
        "created_at": updated_data.get("created_at"),
        "updated_at": updated_data.get("updated_at"),
        "assigned_to": updated_data.get("assigned_to"),
        "reporter_uid": updated_data.get("reporter_uid")
    }
    
    return ReportPublic(**response_data)


# Endpoint específico para encargados para listar sus reportes asignados
@router.get("/assigned-reports/", response_model=List[dict])
def list_assigned_reports(
    status: Optional[ReportStatus] = Query(None),
    priority: Optional[ReportPriority] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user.get("id")
    user_role = current_user.get("role")
    
    # Verificación de rol exclusivo para encargados
    if user_role != UserRole.ENCARGADO:
        raise HTTPException(
            status_code=403, 
            detail="Esta ruta es solo para encargados"
        )
    
    reports_ref = db.collection("reports")
    reports_ref = reports_ref.where("assigned_to", "==", user_id)
    
    # Aplicación de filtros opcionales de estado y prioridad
    if status:
        reports_ref = reports_ref.where("status", "==", status.value)
    if priority:
        reports_ref = reports_ref.where("priority", "==", priority.value)
    
    # Recopilación y transformación de reportes asignados
    reports = []
    for doc in reports_ref.stream():
        report_data = doc.to_dict()
        
        report_response = {
            "id": doc.id,
            "description": report_data.get("description"),
            "location": report_data.get("location"),
            "images": report_data.get("images", []),
            "priority": report_data.get("priority"),
            "status": report_data.get("status"),
            "created_at": report_data.get("created_at"),
            "updated_at": report_data.get("updated_at"),
            "assigned_to": report_data.get("assigned_to"),
            "reporter_uid": report_data.get("reporter_uid"),
            "is_anonymous_public": report_data.get("is_anonymous_public", False)
        }
        
        reports.append(report_response)
    
    # Ordenamiento cronológico inverso de reportes
    reports.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    return reports
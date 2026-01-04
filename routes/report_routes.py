# report_routes.py
from fastapi import APIRouter, HTTPException, Depends, Query, status, Form, File, UploadFile
from typing import List, Optional
from datetime import datetime
import uuid

from services.cloudinary_client import cloudinary
import cloudinary.uploader
from services.firebase_client import db
from models.report import Report, ReportCreate, ReportPublic, ReportLocation
from models.enums import ReportStatus, ReportPriority, UserRole, NotificationType
from models.notification import NotificationCreate
from routes.auth_routes import get_current_user

router = APIRouter(tags=["Reports"])


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
    
    notification_data["id"] = str(uuid.uuid4())
    notification_data["created_at"] = datetime.utcnow()
    
    db.collection("notifications").document(notification_data["id"]).set(notification_data)


# -------------------- Crear reporte -------------------- #
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
    """
    Crea un nuevo reporte con subida de imágenes a Cloudinary.
    Solo reportantes pueden crear reportes.
    """
    if not is_reportante(current_user):
        raise HTTPException(
            status_code=403, 
            detail="Solo los reportantes pueden crear reportes"
        )
    
    user_id = current_user.get("id")
    username = current_user.get("username", "unknown")
    
    # 1. Subir imágenes a Cloudinary (SIN convertir a bytes)
    image_urls = []
    if images:
        for image in images:
            try:
                # Subir directamente el archivo a Cloudinary
                upload_result = cloudinary.uploader.upload(
                    image.file,  # Archivo directo, SIN leer bytes
                    folder=f"comunimapp/reports/{username}",
                    public_id=f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{image.filename}",
                    overwrite=True
                )
                image_urls.append(upload_result["secure_url"])
            except Exception as e:
                raise HTTPException(
                    status_code=500, 
                    detail=f"Error subiendo imagen {image.filename}: {str(e)}"
                )
    
    # 2. Crear objeto location
    location = ReportLocation(
        latitude=latitude,
        longitude=longitude,
        address=address,
        city=city
    )
    
    # 3. Generar ID único para el reporte
    report_id = str(uuid.uuid4())
    created_at = datetime.utcnow()
    
    # 4. Crear objeto Report para Firestore
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
    
    # 5. Guardar en Firestore
    db.collection("reports").document(report_id).set(report_dict)
    
    # 6. Crear notificación para el reportante
    create_notification(
        user_id=user_id,
        report_id=report_id,
        title="Reporte creado exitosamente",
        message=f"Tu reporte ha sido creado y está pendiente de revisión",
        notification_type=NotificationType.ASIGNACION_CASO
    )
    
    # 7. Buscar admins para notificarles
    admins_ref = db.collection("users").where("role", "==", UserRole.ADMIN.value).stream()
    for admin_doc in admins_ref:
        admin_data = admin_doc.to_dict()
        create_notification(
            user_id=admin_data.get("id"),
            report_id=report_id,
            title="Nuevo reporte pendiente",
            message=f"Hay un nuevo reporte pendiente de asignación",
            notification_type=NotificationType.ASIGNACION_CASO
        )
    
    # 8. Preparar respuesta pública
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
    
    # Aplicar anonimato si corresponde
    response_data["reporter_uid"] = None if is_anonymous else user_id
    
    return ReportPublic(**response_data)


# -------------------- Listar reportes (con filtros) -------------------- #
@router.get("/", response_model=List[ReportPublic])
def list_reports(
    status: Optional[ReportStatus] = Query(None),
    priority: Optional[ReportPriority] = Query(None),
    assigned_to_me: Optional[bool] = Query(None, description="Filtrar solo reportes asignados a mí"),
    current_user: dict = Depends(get_current_user)
):
    """
    Lista reportes según el rol del usuario:
    - Admin: Ve todos los reportes
    - Encargado: Ve reportes asignados a él
    - Reportante: Ve solo sus propios reportes
    """
    user_id = current_user.get("id")
    user_role = current_user.get("role")
    
    reports_ref = db.collection("reports")
    
    # Aplicar filtros comunes
    if status:
        reports_ref = reports_ref.where("status", "==", status.value)
    if priority:
        reports_ref = reports_ref.where("priority", "==", priority.value)
    
    # Filtrar según rol
    if user_role == UserRole.ADMIN:
        # Admin ve todo, no necesita filtro adicional
        pass
    elif user_role == UserRole.ENCARGADO:
        if assigned_to_me:
            # Solo reportes asignados a este encargado
            reports_ref = reports_ref.where("assigned_to", "==", user_id)
        else:
            # Encargado ve reportes asignados a él
            reports_ref = reports_ref.where("assigned_to", "==", user_id)
    elif user_role == UserRole.REPORTANTE:
        # Reportante ve solo sus reportes
        reports_ref = reports_ref.where("reporter_uid", "==", user_id)
    else:
        raise HTTPException(status_code=403, detail="Rol no autorizado")
    
    reports = []
    for doc in reports_ref.stream():
        report_data = doc.to_dict()
        report_id = report_data.get("id")
        
        # Preparar respuesta pública
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
        
        # Determinar visibilidad de reporter_uid
        is_anonymous = report_data.get("is_anonymous_public", False)
        can_see_reporter = (
            user_role == UserRole.ADMIN or  # Admin siempre ve
            user_id == report_data.get("reporter_uid")  # Propio reportante
        )
        
        if can_see_reporter or not is_anonymous:
            response_data["reporter_uid"] = report_data.get("reporter_uid")
        else:
            response_data["reporter_uid"] = None
        
        reports.append(ReportPublic(**response_data))
    
    return reports


# -------------------- Obtener reporte específico -------------------- #
@router.get("/{report_id}", response_model=ReportPublic)
def get_report(
    report_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Obtiene un reporte específico por ID.
    Verificación de permisos según rol.
    """
    doc = db.collection("reports").document(report_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    
    report_data = doc.to_dict()
    user_id = current_user.get("id")
    user_role = current_user.get("role")
    
    # Verificar permisos
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
    
    # Preparar respuesta
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
    
    # Determinar visibilidad de reporter_uid
    is_anonymous = report_data.get("is_anonymous_public", False)
    can_see_reporter = (
        user_role == UserRole.ADMIN or  # Admin siempre ve
        user_id == reporter_uid  # Propio reportante
    )
    
    if can_see_reporter or not is_anonymous:
        response_data["reporter_uid"] = reporter_uid
    else:
        response_data["reporter_uid"] = None
    
    return ReportPublic(**response_data)


# -------------------- Asignar reporte a encargado -------------------- #
@router.put("/{report_id}/assign", response_model=ReportPublic)
def assign_report(
    report_id: str,
    encargado_id: str = Query(..., description="ID del encargado a asignar"),
    current_user: dict = Depends(get_current_user)
):
    """
    Asigna un reporte a un encargado.
    Solo administradores pueden asignar reportes.
    """
    if not is_admin(current_user):
        raise HTTPException(
            status_code=403, 
            detail="Solo administradores pueden asignar reportes"
        )
    
    # Verificar que el reporte existe
    report_ref = db.collection("reports").document(report_id)
    report_doc = report_ref.get()
    
    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    
    report_data = report_doc.to_dict()
    
    # Verificar que el reporte esté pendiente
    if report_data.get("status") != ReportStatus.PENDIENTE:
        raise HTTPException(
            status_code=400, 
            detail=f"El reporte ya está en estado: {report_data.get('status')}"
        )
    
    # Verificar que el encargado existe y es encargado
    encargado_doc = db.collection("users").document(encargado_id).get()
    if not encargado_doc.exists:
        raise HTTPException(status_code=404, detail="Encargado no encontrado")
    
    encargado_data = encargado_doc.to_dict()
    if encargado_data.get("role") != UserRole.ENCARGADO:
        raise HTTPException(status_code=400, detail="El usuario no es un encargado")
    
    # Actualizar reporte
    update_time = datetime.utcnow()
    report_ref.update({
        "assigned_to": encargado_id,
        "status": ReportStatus.ASIGNADO,
        "updated_at": update_time
    })
    
    # Obtener reporte actualizado
    updated_doc = report_ref.get()
    updated_data = updated_doc.to_dict()
    
    # Crear notificaciones
    reporter_uid = updated_data.get("reporter_uid")
    
    # Notificar al reportante
    create_notification(
        user_id=reporter_uid,
        report_id=report_id,
        title="Reporte asignado",
        message=f"Tu reporte ha sido asignado a un encargado",
        notification_type=NotificationType.ASIGNACION_CASO
    )
    
    # Notificar al encargado
    create_notification(
        user_id=encargado_id,
        report_id=report_id,
        title="Nuevo reporte asignado",
        message="Se te ha asignado un nuevo reporte",
        notification_type=NotificationType.ASIGNACION_CASO
    )
    
    # Preparar respuesta
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
        "reporter_uid": reporter_uid  # Admin siempre ve reporter_uid
    }
    
    return ReportPublic(**response_data)


# -------------------- Eliminar reporte -------------------- #
@router.delete("/{report_id}")
def delete_report(
    report_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Elimina un reporte.
    - Reportante: Solo si el reporte está PENDIENTE y es suyo
    - Admin: Puede eliminar cualquier reporte
    """
    user_id = current_user.get("id")
    user_role = current_user.get("role")
    
    report_ref = db.collection("reports").document(report_id)
    report_doc = report_ref.get()
    
    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    
    report_data = report_doc.to_dict()
    reporter_uid = report_data.get("reporter_uid")
    report_status = report_data.get("status")
    
    # Verificar permisos
    if user_role == UserRole.ADMIN:
        # Admin puede eliminar cualquier reporte
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
    
    # Eliminar reporte
    report_ref.delete()
    
    # Eliminar notificaciones relacionadas
    notifications_ref = db.collection("notifications").where("report_id", "==", report_id).stream()
    for notif_doc in notifications_ref:
        notif_doc.reference.delete()
    
    return {"message": "Reporte eliminado correctamente"}


# -------------------- Actualizar estado del reporte -------------------- #
@router.patch("/{report_id}/status", response_model=ReportPublic)
def update_report_status(
    report_id: str,
    new_status: ReportStatus = Query(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Actualiza el estado de un reporte.
    - Encargado: Puede cambiar estado de reportes asignados a él
    - Admin: Puede cambiar estado de cualquier reporte
    """
    user_id = current_user.get("id")
    user_role = current_user.get("role")
    
    report_ref = db.collection("reports").document(report_id)
    report_doc = report_ref.get()
    
    if not report_doc.exists:
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    
    report_data = report_doc.to_dict()
    assigned_to = report_data.get("assigned_to")
    
    # Verificar permisos
    if user_role == UserRole.ADMIN:
        # Admin puede cambiar cualquier estado
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
    
    # Validar transiciones de estado
    current_status = report_data.get("status")
    
    # Solo permitir ciertas transiciones
    valid_transitions = {
        ReportStatus.PENDIENTE: [ReportStatus.ASIGNADO],
        ReportStatus.ASIGNADO: [ReportStatus.EN_PROCESO, ReportStatus.PENDIENTE],
        ReportStatus.EN_PROCESO: [ReportStatus.RESUELTO, ReportStatus.ASIGNADO],
        ReportStatus.RESUELTO: [ReportStatus.CERRADO, ReportStatus.EN_PROCESO],
        ReportStatus.CERRADO: []  # Cerrado es final
    }
    
    if current_status == ReportStatus.CERRADO:
        raise HTTPException(status_code=400, detail="Reporte ya está cerrado")
    
    if new_status not in valid_transitions.get(current_status, []):
        raise HTTPException(
            status_code=400, 
            detail=f"Transición de estado inválida: {current_status} -> {new_status}"
        )
    
    # Actualizar reporte
    update_time = datetime.utcnow()
    report_ref.update({
        "status": new_status.value,
        "updated_at": update_time
    })
    
    # Obtener reporte actualizado
    updated_doc = report_ref.get()
    updated_data = updated_doc.to_dict()
    
    # Crear notificación si cambia a CERRADO
    if new_status == ReportStatus.CERRADO:
        reporter_uid = updated_data.get("reporter_uid")
        
        create_notification(
            user_id=reporter_uid,
            report_id=report_id,
            title="Reporte cerrado",
            message="Tu reporte ha sido cerrado",
            notification_type=NotificationType.CIERRE_CASO
        )
    
    # Preparar respuesta
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
        "reporter_uid": updated_data.get("reporter_uid")  # Admin/encargado ven reporter_uid
    }
    
    return ReportPublic(**response_data)

# -------------------- Listar reportes asignados a un encargado -------------------- #
@router.get("/assigned-reports/", response_model=List[dict])
def list_assigned_reports(
    status: Optional[ReportStatus] = Query(None),
    priority: Optional[ReportPriority] = Query(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Lista reportes asignados al encargado actual.
    SOLO para usuarios con rol ENCARGADO.
    """
    user_id = current_user.get("id")
    user_role = current_user.get("role")
    
    # Verificar que el usuario es encargado
    if user_role != UserRole.ENCARGADO:
        raise HTTPException(
            status_code=403, 
            detail="Esta ruta es solo para encargados"
        )
    
    # Construir query
    reports_ref = db.collection("reports")
    
    # Filtrar por reportes asignados a este encargado
    reports_ref = reports_ref.where("assigned_to", "==", user_id)
    
    # Aplicar filtros opcionales
    if status:
        reports_ref = reports_ref.where("status", "==", status.value)
    if priority:
        reports_ref = reports_ref.where("priority", "==", priority.value)
    
    # Obtener reportes
    reports = []
    for doc in reports_ref.stream():
        report_data = doc.to_dict()
        
        # Preparar respuesta
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
    
    # Ordenar por fecha de creación (más recientes primero)
    reports.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    return reports
import os
import jwt as pyjwt
from fastapi import APIRouter, HTTPException, Query, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from collections import Counter
from datetime import datetime, timedelta
from cachetools import TTLCache
from enum import Enum
from typing import Dict, Optional
from pydantic import BaseModel
import pytz

# ==============================================================================
# 1. IMPORTACION DEL MOTOR DE IA (Microservicio Interno)
# ==============================================================================
try:
    from services.ai_engine import generar_reporte_ia, KPIDataMock

    print("[INFO] Modulo de IA importado correctamente.")
except ImportError as e:
    print(f"[WARNING] Error importando modulo de IA: {e}")

    # Clases Mock (Dummy) para mantener la integridad del sistema si falta la IA
    def generar_reporte_ia(*args):
        return None

    class KPIDataMock(BaseModel):
        total_reportes: int = 0
        casos_activos: int = 0
        tasa_resolucion_label: str = "0%"


# ==============================================================================
# 2. CONEXION A BASE DE DATOS
# ==============================================================================
try:
    from services.firebase_client import db

    print("[INFO] Conexion a base de datos Firebase establecida.")
except ImportError:
    print("[CRITICAL] No se encuentra el modulo 'services/firebase_client.py'.")
    exit(1)

# ==============================================================================
# 3. SEGURIDAD Y AUTENTICACION
# ==============================================================================
JWT_SECRET = os.getenv("JWT_SECRET", "supersecretkey")
JWT_ALGORITHM = "HS256"
security = HTTPBearer()


def decode_jwt(token: str) -> Optional[dict]:
    """
    Decodifica y valida la firma del token JWT.
    """
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except pyjwt.PyJWTError:
        return None


async def get_current_user_real(
    credentials: HTTPAuthorizationCredentials = Security(security),
):
    """
    Middleware de dependencia para validar la sesion del usuario.
    """
    token = credentials.credentials
    payload = decode_jwt(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Token de autenticacion invalido")

    uid = payload.get("sub")
    doc = db.collection("users").document(uid).get()

    if not doc.exists:
        raise HTTPException(
            status_code=404, detail="Usuario no encontrado en el sistema"
        )

    user_data = doc.to_dict()
    user_data["id"] = uid
    return user_data


# ==============================================================================
# 4. CONFIGURACION DEL NEGOCIO
# ==============================================================================
TIMEZONE = pytz.timezone("America/Guayaquil")
metrics_cache = TTLCache(maxsize=100, ttl=15)


class UserRole(str, Enum):
    ADMIN = "admin"
    ENCARGADO = "encargado"
    REPORTANTE = "reportante"


class ReportStatus(str, Enum):
    PENDIENTE = "pendiente"
    ASIGNADO = "asignado"
    EN_PROCESO = "en_proceso"
    RESUELTO = "resuelto"
    CERRADO = "cerrado"
    FINALIZADO = "finalizado"


CLOSED_STATUSES = {ReportStatus.RESUELTO, ReportStatus.CERRADO, ReportStatus.FINALIZADO}
OPEN_STATUSES = {ReportStatus.PENDIENTE, ReportStatus.ASIGNADO, ReportStatus.EN_PROCESO}

# ==============================================================================
# 5. MODELOS DE TRANSFERENCIA DE DATOS (DTOs)
# ==============================================================================


class KPIData(BaseModel):
    total_reportes: int
    casos_activos: int
    tasa_resolucion: float
    tasa_resolucion_label: str
    tasa_transparencia: float
    tasa_evidencia: float
    mensaje_alerta: str


class AIAnalysis(BaseModel):
    titulo: str
    mensaje: str
    color_alerta: str


class DashboardResponse(BaseModel):
    kpis_negocio: KPIData
    ai_analisis: AIAnalysis
    graficas: Dict[str, Dict[str, int]]


# ==============================================================================
# 6. CAPA DE SERVICIO (LOGICA DE NEGOCIO)
# ==============================================================================


class MetricsService:
    @staticmethod
    def get_date_range(time_range: str):
        now_local = datetime.now(TIMEZONE)
        if time_range == "dia":
            return now_local.replace(
                hour=0, minute=0, second=0, microsecond=0
            ).astimezone(pytz.utc)
        elif time_range == "semana":
            return (now_local - timedelta(days=7)).astimezone(pytz.utc)
        elif time_range == "mes":
            return (now_local - timedelta(days=30)).astimezone(pytz.utc)
        return None

    @staticmethod
    def calculate_metrics(docs, status_filter: str, usar_ia: bool) -> DashboardResponse:
        total_filtered = 0
        resolved_count = 0
        status_counts = Counter()
        priority_counts = Counter()
        city_counts = Counter()
        anonymous_count = 0
        public_count = 0
        evidence_count = 0

        for doc in docs:
            data = doc.to_dict()
            status_raw = str(data.get("status", "pendiente")).lower()

            if status_filter == "abiertos" and status_raw not in OPEN_STATUSES:
                continue
            if status_filter == "cerrados" and status_raw not in CLOSED_STATUSES:
                continue
            if (
                status_filter not in ["todos", "abiertos", "cerrados"]
                and status_raw != status_filter
            ):
                continue

            total_filtered += 1
            if status_raw in CLOSED_STATUSES:
                resolved_count += 1

            status_counts[status_raw] += 1
            priority_counts[str(data.get("priority", "media")).lower()] += 1
            city = data.get("location", {}).get("city", "Desconocida")
            city_counts[city] += 1

            if data.get("is_anonymous_public", False):
                anonymous_count += 1
            else:
                public_count += 1
            if data.get("images"):
                evidence_count += 1

        resolution_rate = (
            round((resolved_count / total_filtered * 100), 1)
            if total_filtered > 0
            else 0.0
        )
        active_cases = total_filtered - resolved_count

        alert_msg = "Normal"
        if active_cases > 50:
            alert_msg = "Alto Trafico"
        if resolution_rate < 40 and total_filtered > 10:
            alert_msg = "Critico"

        kpi_final = KPIData(
            total_reportes=total_filtered,
            casos_activos=active_cases,
            tasa_resolucion=resolution_rate,
            tasa_resolucion_label=f"{resolution_rate}%",
            tasa_transparencia=(
                round((public_count / total_filtered * 100), 1) if total_filtered else 0
            ),
            tasa_evidencia=(
                round((evidence_count / total_filtered * 100), 1)
                if total_filtered
                else 0
            ),
            mensaje_alerta=alert_msg,
        )

        graficas_final = {
            "por_estado": dict(status_counts),
            "por_prioridad": dict(priority_counts),
            "top_zonas_riesgo": dict(city_counts.most_common(5)),
            "anonimato": {"anonimos": anonymous_count, "publicos": public_count},
        }

        # ---------------------------------------------------------
        # INTEGRACION DE INTELIGENCIA ARTIFICIAL (BAJO DEMANDA)
        # ---------------------------------------------------------

        ai_insight = AIAnalysis(
            titulo="Analisis IA Pendiente",
            mensaje="Presiona Generar para ver el reporte inteligente.",
            color_alerta="gray",
        )

        if usar_ia:
            print("[INFO] Procesando solicitud de analisis con IA (On-Demand)...")
            try:
                datos_ia = KPIDataMock(
                    total_reportes=kpi_final.total_reportes,
                    casos_activos=kpi_final.casos_activos,
                    tasa_resolucion_label=kpi_final.tasa_resolucion_label,
                )

                resultado_ia = generar_reporte_ia(
                    datos_ia, list(city_counts.most_common(5)), dict(priority_counts)
                )

                if resultado_ia:
                    ai_insight = AIAnalysis(
                        titulo=resultado_ia.titulo,
                        mensaje=resultado_ia.mensaje,
                        color_alerta=resultado_ia.color_alerta,
                    )
                else:
                    print("[WARNING] El motor de IA no devolvio resultados.")
                    ai_insight = AIAnalysis(
                        titulo="Error IA",
                        mensaje="Generacion fallida.",
                        color_alerta="red",
                    )

            except Exception as e:
                print(f"[ERROR] Excepcion durante el procesamiento de IA: {e}")
                ai_insight = AIAnalysis(
                    titulo="Fallo de Sistema",
                    mensaje="Error interno del motor.",
                    color_alerta="red",
                )

        return DashboardResponse(
            kpis_negocio=kpi_final, ai_analisis=ai_insight, graficas=graficas_final
        )


# ==============================================================================
# 7. DEFINICION DEL ROUTER (MODULO)
# ==============================================================================

router = APIRouter(tags=["Metricas"])


@router.get("/dashboard", response_model=DashboardResponse)
async def get_metrics_dashboard(
    time_range: str = Query("historico", alias="range"),
    status_type: str = Query("todos"),
    analyze_ai: bool = Query(
        False, description="Activa el analisis generativo si es True"
    ),
    current_user: dict = Depends(get_current_user_real),
):
    """
    Endpoint principal del dashboard. Retorna KPIs, graficas y analisis opcional.
    """

    if current_user.get("role") not in [UserRole.ADMIN.value, UserRole.ENCARGADO.value]:
        raise HTTPException(status_code=403, detail="Permisos insuficientes")

    try:
        cache_key = f"dash_{time_range}_{status_type}_ai{analyze_ai}"

        if cache_key in metrics_cache:
            return metrics_cache[cache_key]

        print(
            f"[INFO] Calculando Metricas | IA: {analyze_ai} | Usuario: {current_user.get('username')}"
        )

        start_date_utc = MetricsService.get_date_range(time_range)
        query = db.collection("reports")
        if start_date_utc:
            query = query.where("created_at", ">=", start_date_utc)

        docs = list(query.stream())

        response_data = MetricsService.calculate_metrics(docs, status_type, analyze_ai)

        metrics_cache[cache_key] = response_data
        return response_data

    except Exception as e:
        print(f"[ERROR] Error interno en endpoint de metricas: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

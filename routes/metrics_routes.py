from fastapi import APIRouter, HTTPException
from services.firebase_client import db
from collections import Counter
from datetime import datetime
import sys

# Inicialización del Router
router = APIRouter()


@router.get("/")
async def get_metrics_data():
    """
    Endpoint de Métricas Generales.
    Retorna KPIs y estadísticas de negocio en tiempo real.
    """
    try:
        # Recuperación optimizada de documentos (stream)
        reports_ref = db.collection("reports")
        docs = reports_ref.stream()

        # --- Inicialización de Variables ---
        total_reports = 0
        status_counts = Counter()
        priority_counts = Counter()
        recent_activity = []
        city_counts = Counter()
        dates_last_7_days = []

        # Variables para KPI de eficiencia
        total_waiting_hours = 0
        pending_reports_count = 0
        now = datetime.utcnow()

        # --- Procesamiento de Datos (O(n)) ---
        for doc in docs:
            data = doc.to_dict()
            total_reports += 1

            # 1. Normalización
            status = str(data.get("status", "sin_estado")).lower()
            priority = str(data.get("priority", "sin_prioridad")).lower()

            # 2. Datos Geográficos
            location = data.get("location", {})
            city = "Desconocida"
            if isinstance(location, dict):
                city = location.get("city", "Desconocida")
            city_counts[city] += 1

            # 3. KPI: Tiempo Promedio de Espera & Tendencia
            created_at = data.get("created_at")
            dt_object = None

            if created_at:
                try:
                    if isinstance(created_at, str):
                        dt_object = datetime.fromisoformat(
                            created_at.replace("Z", "+00:00")
                        )
                    else:
                        dt_object = created_at

                    if status in ["pendiente", "asignado", "en_proceso"] and dt_object:
                        delta = now.replace(tzinfo=None) - dt_object.replace(
                            tzinfo=None
                        )
                        total_waiting_hours += delta.total_seconds() / 3600
                        pending_reports_count += 1

                        if delta.days <= 7:
                            date_str = dt_object.strftime("%Y-%m-%d")
                            dates_last_7_days.append(date_str)
                except Exception:
                    pass

            # 4. Conteos Generales
            status_counts[status] += 1
            priority_counts[priority] += 1

            # 5. Feed de Actividad
            recent_activity.append(
                {
                    "id": doc.id,
                    "description": data.get("description", "Sin descripción")[:50]
                    + "...",
                    "priority": priority,
                    "status": status,
                    "date": str(created_at) if created_at else "N/A",
                    "raw_date": dt_object,
                }
            )

        # --- Post-Procesamiento ---

        recent_activity_clean = [r for r in recent_activity if r["raw_date"]]
        recent_activity_clean.sort(key=lambda x: str(x["raw_date"]), reverse=True)

        feed_final = []
        for item in recent_activity_clean[:5]:
            item.pop("raw_date", None)
            feed_final.append(item)

        avg_wait_hours = 0
        if pending_reports_count > 0:
            avg_wait_hours = round(total_waiting_hours / pending_reports_count, 1)

        trend_counts = Counter(dates_last_7_days)
        sorted_trend = dict(sorted(trend_counts.items()))
        top_cities = dict(city_counts.most_common(3))

        return {
            "kpis_negocio": {
                "total_reportes": total_reports,
                "casos_activos": pending_reports_count,
                "tiempo_promedio_espera_horas": avg_wait_hours,
                "mensaje_alerta": "Critico" if avg_wait_hours > 24 else "Normal",
            },
            "graficas": {
                "por_prioridad": dict(priority_counts),
                "por_estado": dict(status_counts),
                "top_zonas_riesgo": top_cities,
                "tendencia_semanal": sorted_trend,
            },
            "feed_tiempo_real": feed_final,
        }

    except Exception as e:
        print(f"[ERROR CRÍTICO] Fallo en cálculo de métricas: {e}")
        raise HTTPException(status_code=500, detail="Error interno procesando métricas")

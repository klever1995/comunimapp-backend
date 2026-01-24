import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from collections import Counter
from datetime import datetime, timedelta
from cachetools import TTLCache

try:
    from services.firebase_client import db

    print("✅ Conexión a Firebase importada correctamente.")
except ImportError:
    print("❌ ERROR CRÍTICO: No se encuentra 'services/firebase_client.py'.")
    exit(1)

app = FastAPI(title="Test Server - Métricas Finales")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

metrics_cache = TTLCache(maxsize=32, ttl=5)


@app.get("/metrics")
async def get_metrics_data(
    range: str = Query("historico"), status_type: str = Query("todos")
):
    try:
        cache_key = f"dashboard_{range}_{status_type}"
        if cache_key in metrics_cache:
            return metrics_cache[cache_key]

        print(f"🔄 Calculando Eficacia. Tiempo: {range} | Estado: {status_type}")

        # 1. LEER DATOS
        reports_docs = list(db.collection("reports").stream())
        # (Ya no necesitamos leer updates para tiempos, más rápido)

        now = datetime.utcnow()

        # 2. FILTROS DE TIEMPO
        start_date = None
        if range == "dia":
            start_date = now - timedelta(hours=24)
        elif range == "semana":
            start_date = now - timedelta(days=7)
        elif range == "mes":
            start_date = now - timedelta(days=30)

        # Definir grupos
        closed_statuses = ["resuelto", "cerrado", "finalizado"]
        open_statuses = ["pendiente", "asignado", "en_proceso"]

        # Variables
        total_filtered = 0
        resolved_count_in_period = 0  # Cuántos de estos están resueltos

        status_counts = Counter()
        priority_counts = Counter()
        city_counts = Counter()
        anonymous_count = 0
        public_count = 0
        reports_with_photos = 0

        # --- CICLO ÚNICO ---
        for doc in reports_docs:
            data = doc.to_dict()

            # A. Filtro Fecha
            created_at = data.get("created_at")
            dt_obj = None
            if isinstance(created_at, str):
                try:
                    dt_obj = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00").split(".")[0]
                    )
                except:
                    pass
            else:
                dt_obj = created_at

            if start_date and dt_obj:
                if dt_obj.replace(tzinfo=None) < start_date:
                    continue

            # B. Filtro Estado (El que pide el usuario)
            status_raw = str(data.get("status", "pendiente")).lower()

            # Lógica de filtrado visual
            if status_type != "todos":
                if status_type == "abiertos" and status_raw not in open_statuses:
                    continue
                elif status_type == "cerrados" and status_raw not in closed_statuses:
                    continue
                elif (
                    status_type not in ["abiertos", "cerrados"]
                    and status_raw != status_type
                ):
                    continue

            # --- SI PASA FILTROS, CONTAMOS ---
            total_filtered += 1

            # Contar si este caso específico cuenta como "Éxito" (Resuelto)
            if status_raw in closed_statuses:
                resolved_count_in_period += 1

            # Llenar gráficas
            status_counts[status_raw] += 1
            priority_counts[str(data.get("priority", "media")).lower()] += 1
            city = data.get("location", {}).get("city", "Desconocida")
            if city and city != "Desconocida":
                city_counts[city] += 1
            if data.get("is_anonymous_public", False):
                anonymous_count += 1
            else:
                public_count += 1
            if data.get("images"):
                reports_with_photos += 1

        # --- CÁLCULO DE LA NUEVA MÉTRICA: TASA DE EFICACIA ---

        efficiency_rate = 0
        if total_filtered > 0:
            efficiency_rate = round(
                (resolved_count_in_period / total_filtered) * 100, 1
            )

        # Preparamos el mensaje de la tarjeta
        # Reutilizamos el campo 'tiempo_formato' para mandar el porcentaje string "85%"
        kpi_display_value = f"{efficiency_rate}%"
        kpi_label = "Tasa Eficacia"

        response_data = {
            "kpis_negocio": {
                "total_reportes": total_filtered,
                "casos_activos": total_filtered
                - resolved_count_in_period,  # Pendientes reales
                # --- AQUÍ VA LA NUEVA MÉTRICA EN LUGAR DEL TIEMPO ---
                "tiempo_promedio_espera_horas": efficiency_rate,  # Valor numérico
                "tiempo_formato": kpi_display_value,  # String "80%"
                "etiqueta_tiempo": kpi_label,  # "Tasa Eficacia"
                "tasa_transparencia": (
                    round((public_count / total_filtered) * 100, 1)
                    if total_filtered > 0
                    else 0
                ),
                "tasa_evidencia": (
                    round((reports_with_photos / total_filtered) * 100, 1)
                    if total_filtered > 0
                    else 0
                ),
                "productividad_semanal": 0,
                "mensaje_alerta": "Normal",
            },
            "graficas": {
                "por_estado": dict(status_counts),
                "por_prioridad": dict(priority_counts),
                "top_zonas_riesgo": dict(city_counts),
                "anonimato": {"anonimos": anonymous_count, "publicos": public_count},
            },
        }
        metrics_cache[cache_key] = response_data
        return response_data

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

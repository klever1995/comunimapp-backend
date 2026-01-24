import os
import google.generativeai as genai
from pydantic import BaseModel
from dotenv import load_dotenv

# ==============================================================================
# 1. CONFIGURACION DEL MOTOR GENERATIVO
# ==============================================================================
load_dotenv()

# Recuperacion de credenciales
GEMINI_API_KEY = os.getenv("API_KEY_AIGOOGLE")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    # Log de advertencia critico si no hay credenciales
    print("[CRITICAL] API Key de Google no encontrada en variables de entorno.")

# Seleccion del modelo optimizado para baja latencia
# Se utiliza la version 'latest' del modelo Flash para garantizar compatibilidad
MODEL_NAME = "models/gemini-flash-latest"

try:
    model = genai.GenerativeModel(MODEL_NAME)
    print(f"[INFO] Motor de IA inicializado: {MODEL_NAME}")
except Exception as e:
    print(f"[ERROR] Fallo en la inicializacion del modelo: {e}")

# ==============================================================================
# 2. DEFINICION DE MODELOS DE DATOS
# ==============================================================================


class KPIDataMock(BaseModel):
    """
    Estructura de datos simplificada para la ingesta del motor de IA.
    Contiene los indicadores clave necesarios para el analisis contextual.
    """

    total_reportes: int
    casos_activos: int
    tasa_resolucion_label: str


class AIAnalysisResult(BaseModel):
    """
    Estructura estandarizada para la respuesta generada.
    Garantiza consistencia en el consumo por parte del frontend.
    """

    titulo: str
    mensaje: str
    color_alerta: str  # Valores permitidos: 'red', 'yellow', 'green', 'blue', 'gray'


# ==============================================================================
# 3. LOGICA DE GENERACION (CORE)
# ==============================================================================


def generar_reporte_ia(
    kpis: KPIDataMock, zonas_riesgo: list, prioridades: dict
) -> AIAnalysisResult:
    """
    Genera un analisis operativo breve basado en metricas en tiempo real.

    Args:
        kpis (KPIDataMock): Objeto con los indicadores numericos principales.
        zonas_riesgo (list): Lista de zonas con mayor incidencia.
        prioridades (dict): Distribucion de casos por nivel de prioridad.

    Returns:
        AIAnalysisResult: Objeto con titulo, mensaje estrategico y color de semaforo.
                          Retorna un objeto de error controlado en caso de fallo.
    """
    print("[INFO] Iniciando solicitud de inferencia a Google Gemini...")

    try:
        # Construccion del prompt con tecnica de Few-Shot implicita y restricciones de formato
        prompt = f"""
        Rol: Analista de Seguridad y Operaciones.
        
        Contexto de Datos:
        - Incidentes Totales: {kpis.total_reportes}
        - Casos Pendientes: {kpis.casos_activos}
        - Eficiencia de Resolucion: {kpis.tasa_resolucion_label}
        - Zonas Criticas: {zonas_riesgo}
        - Distribucion de Prioridad: {prioridades}
        
        Instruccion:
        Analiza la situacion actual y genera una alerta ejecutiva.
        
        Formato de Respuesta Requerido (Texto plano separado por tuberias):
        TITULO|MENSAJE|COLOR
        
        Reglas de Negocio:
        1. TITULO: Maximo 5 palabras. Conciso y directo.
        2. MENSAJE: Maximo 20 palabras. Debe sugerir una accion tactica.
        3. COLOR: 
           - 'red': Si resolucion < 50% o pendientes > 20 (Situacion Critica).
           - 'yellow': Si hay acumulacion moderada (Precaucion).
           - 'green': Si la operacion es estable (Optimo).
        """

        # Ejecucion de la inferencia
        response = model.generate_content(prompt)
        texto_respuesta = response.text.strip()

        # Validacion y parseo de la respuesta
        partes = texto_respuesta.split("|")

        if len(partes) >= 3:
            return AIAnalysisResult(
                titulo=partes[0].strip(),
                mensaje=partes[1].strip(),
                color_alerta=partes[2].strip().lower(),
            )
        else:
            # Mecanismo de fallback para respuestas no estructuradas
            return AIAnalysisResult(
                titulo="Reporte IA Generado",
                mensaje=texto_respuesta[:100],
                color_alerta="blue",
            )

    except Exception as e:
        error_msg = str(e)

        # Manejo especifico de errores de cuota (Rate Limit)
        if "429" in error_msg:
            print("[WARNING] Limite de cuota de API excedido (429).")
            return AIAnalysisResult(
                titulo="Servicio Saturado",
                mensaje="El sistema de IA esta ocupado momentaneamente. Intente mas tarde.",
                color_alerta="gray",
            )

        print(f"[ERROR] Excepcion no controlada en motor IA: {error_msg}")
        return AIAnalysisResult(
            titulo="Error de Servicio",
            mensaje="No disponible temporalmente.",
            color_alerta="gray",
        )

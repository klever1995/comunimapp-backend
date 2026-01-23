# main.py - Punto de entrada principal de la aplicación FastAPI
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import auth_routes
from routes import user_routes
from routes import report_routes
from routes import case_routes
from routes import notification_routes
from routes import metrics_routes

# Configuración de la aplicación FastAPI con metadatos descriptivos
app = FastAPI(
    title="Comunimapp API",
    description="Backend de Comunimapp: herramienta social para reportar y dar seguimiento a posibles casos de trata o trabajo infantil en espacios públicos, con notificaciones y gestión de casos en tiempo real.",
    version="1.0.0",
)

# Configuración de CORS para comunicación con frontend y aplicaciones móviles
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registro de todos los routers con sus respectivos prefijos de ruta
app.include_router(auth_routes.router, prefix="/auth", tags=["auth"])
app.include_router(user_routes.router, prefix="/users", tags=["users"])
app.include_router(report_routes.router, prefix="/reports", tags=["reports"])
app.include_router(case_routes.router, prefix="/cases", tags=["cases"])
app.include_router(
    notification_routes.router, prefix="/notifications", tags=["notifications"]
)
app.include_router(metrics_routes.router, prefix="/metrics", tags=["metrics"])


# Endpoint de verificación de salud del servidor
@app.get("/")
async def root():
    return {"message": "Comunimapp backend activo"}

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importar routers de cada módulo
from routes import auth_routes
from routes import user_routes
from routes import report_routes
from routes import case_routes
from routes import notification_routes

# Configurar aplicación FastAPI
app = FastAPI(
    title="Comunimapp API",
    description="Backend de Comunimapp: herramienta social para reportar y dar seguimiento a posibles casos de trata o trabajo infantil en espacios públicos, con notificaciones y gestión de casos en tiempo real.",
    version="1.0.0"
)

# Habilitar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar rutas con sus prefijos
app.include_router(auth_routes.router, prefix="/auth", tags=["auth"])
app.include_router(user_routes.router, prefix="/users", tags=["users"])
app.include_router(report_routes.router, prefix="/reports", tags=["reports"])
app.include_router(case_routes.router, prefix="/cases", tags=["cases"]) 
app.include_router(notification_routes.router, prefix="/notifications", tags=["notifications"])

@app.get("/")
async def root():
    return {"message": "Comunimapp backend activo"}

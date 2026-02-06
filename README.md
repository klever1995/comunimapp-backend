### 📢 Sistema de Gestión de Reportes Ciudadanos
**Proyecto UCE - Facultad de Ingeniería y Ciencias Aplicadas**

### 📋 Descripción del Proyecto

API REST desarrollada con **FastAPI** para la gestión de reportes ciudadanos, permitiendo a los usuarios reportar incidencias, asignar responsables, realizar seguimiento y generar análisis estadísticos con inteligencia artificial.

### 🚀 Características Principales

- Autenticación por roles (Reportante, Encargado, Administrador)
- Gestión completa de reportes con geolocalización
- Notificaciones en tiempo real (push y email)
- Sistema de actualizaciones por caso
- Dashboard administrativo con KPIs
- Análisis inteligente con IA (Google Gemini)
- Gestión multimedia con Cloudinary
- API documentada automáticamente (Swagger / OpenAPI)

### 🛠️ Tecnologías Utilizadas

| Componente            | Tecnología                     |
|----------------------|--------------------------------|
| Backend API          | FastAPI (Python 3.9+)          |
| Base de Datos        | Firebase Firestore             |
| Autenticación        | Firebase Auth + JWT            |
| Notificaciones       | Firebase Cloud Messaging       |
| Email                | SendGrid API                   |
| Almacenamiento       | Cloudinary                     |
| Inteligencia Artificial | Google Gemini API           |
| Despliegue           | Render                         |

### 📁 Estructura del Proyecto

```text
backend/
├── models/              # Modelos Pydantic
│   ├── user.py         # Usuarios
│   ├── report.py       # Reportes
│   ├── notification.py # Notificaciones
│   └── case_update.py  # Actualizaciones
├── routes/             # Endpoints API
│   ├── auth_routes.py
│   ├── report_routes.py
│   ├── user_routes.py
│   ├── case_routes.py
│   └── metrics_routes.py
├── services/           # Servicios externos
│   ├── firebase_client.py
│   ├── cloudinary_client.py
│   └── email_client.py
├── requirements.txt    # Dependencias
└── main.py             # Punto de entrada
```

### 🔧 Instalación y Configuración

#### 1. Requisitos Previos
* Python 3.9 o superior
* Cuenta de Firebase
* Cuenta de SendGrid
* Cuenta de Cloudinary
* API Key de Google Gemini

#### 2. Instalación
```bash
# Clonar el repositorio
git clone https://github.com/klever1995/comunimapp-backend.git
cd backend

# Crear entorno virtual
python -m venv venv

# Activar entorno virtual (Linux / MacOS)
source venv/bin/activate

# Activar entorno virtual (Windows)
venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```
#### 3. Configuración de Variables de Entorno

Crear un archivo `.env` en la raíz del proyecto con el siguiente contenido:

```env
# Firebase
FIREBASE_TYPE=service_account
FIREBASE_PROJECT_ID=tu-proyecto
FIREBASE_PRIVATE_KEY_ID=tu-id
FIREBASE_PRIVATE_KEY=tu-llave
FIREBASE_CLIENT_EMAIL=tu-email
FIREBASE_CLIENT_ID=tu-cliente-id

# JWT
JWT_SECRET=tu-secreto-jwt

# SendGrid
SENDGRID_API_KEY=tu-api-key
SENDGRID_FROM_EMAIL=notificaciones@comunimapp.com

# Cloudinary
CLOUDINARY_CLOUD_NAME=tu-cloud
CLOUDINARY_API_KEY=tu-api-key
CLOUDINARY_API_SECRET=tu-secreto

# Google Gemini
API_KEY_AIGOOGLE=tu-api-key-gemini
```
#### 4. Ejecución Local

Ejecutar la aplicación en modo desarrollo:

```bash
# Modo desarrollo
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
Una vez iniciada la aplicación, puedes acceder a la documentación automática de la API:
* Swagger UI: http://localhost:8000/docs
* Redoc: http://localhost:8000/redoc

### 📡 Endpoints Principales

#### 🔐 Autenticación
* `POST /auth/register/reportante` - Registro de reportante
* `POST /auth/register/encargado` - Registro de encargado
* `POST /auth/login` - Inicio de sesión
* `GET /auth/verify-email` - Verificación de email
* `GET /auth/me` - Perfil del usuario

#### 📋 Reportes
* `POST /reports/` - Crear reporte
* `GET /reports/` - Listar reportes (con filtros)
* `GET /reports/{id}` - Obtener reporte específico
* `PUT /reports/{id}/assign` - Asignar reporte
* `PATCH /reports/{id}/status` - Cambiar estado

#### 👥 Usuarios
* `GET /users/me` - Mi perfil
* `PUT /users/me` - Actualizar mi perfil
* `GET /users/{id}` - Obtener usuario
* `GET /users/` - Listar usuarios

#### 📊 Dashboard
* `GET /metrics/dashboard` - KPIs y análisis
    * **Parámetros:** `range`, `status_type`, `analyze_ai`
### 🔐 Roles y Permisos
| Rol            | Permisos                     |
|----------------------|--------------------------------------------------------------------------|
| Reportante           | Crear reportes, ver sus reportes, recibir notificaciones                 |
| Encargado            | Ver reportes asignados, crear actualizaciones, cambiar estado            |
| Administrador        | Gestionar todos los reportes, asignar encargados, ver dashboard completo |

### 📱 Notificaciones

#### Tipos de Notificaciones
1. **Email (SendGrid):** Verificación de cuenta y confirmaciones.
2. **Push (FCM):** Actualizaciones en tiempo real.
3. **En App:** Historial de notificaciones.

#### Eventos que generan notificaciones
* Nuevo reporte creado
* Reporte asignado a encargado
* Actualización en caso
* Cambio de estado
* Cierre de caso
### 📈 Dashboard y Métricas

#### KPIs Calculados
* **Total de reportes:** Volumen general de incidencias registradas.
* **Casos activos/pendientes:** Monitoreo de reportes sin resolver.
* **Tasa de resolución:** Porcentaje de efectividad en el cierre de casos.
* **Distribución por prioridad:** Clasificación por nivel de urgencia.
* **Top zonas de riesgo:** Identificación de sectores críticos mediante geolocalización.
* **Tasa de transparencia:** Medición de reportes anónimos vs. identificados.

#### Análisis con IA
Integración con **Google Gemini API** para potenciar la toma de decisiones:
* **Generación de alertas ejecutivas:** Resúmenes automáticos de situaciones críticas.
* **Análisis de tendencias:** Identificación de patrones recurrentes en los reportes.
* **Recomendaciones estratégicas:** Sugerencias de acción basadas en datos históricos.
* **Reportes automáticos:** Exportación de informes detallados generados por IA.
  
### 🌐 Despliegue en Render

#### 1. Crear cuenta en Render
* Ir a [render.com](https://render.com)
* Registrarse con GitHub o GitLab.

#### 2. Configurar Web Service
Crea un archivo llamado `render.yaml` en la raíz de tu proyecto o configura el servicio manualmente con estos parámetros:

```yaml
# render.yaml
services:
  - type: web
    name: comunimapp-api
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port 10000
    envVars:
      - key: JWT_SECRET
        generateValue: true
      - key: FIREBASE_PROJECT_ID
        sync: false
```

### 🔍 Documentación de API
La API incluye documentación interactiva generada automáticamente:
* **Swagger UI:** `/docs`
* **ReDoc:** `/redoc`
* **Esquema OpenAPI:** `/openapi.json`
### 🧪 Testing
#### Pruebas Locales
```bash
# Instalar dependencias de testing
pip install pytest httpx

# Ejecutar pruebas
pytest tests/
```
### 👥 Contribución

#### Flujo de Trabajo
1. **Fork** del repositorio.
2. Crear **rama feature**: `git checkout -b feature/nueva-funcionalidad`
3. **Commit** de cambios: `git commit -m 'Add nueva funcionalidad'`
4. **Push** a la rama: `git push origin feature/nueva-funcionalidad`
5. Crear un **Pull Request**.

#### Convenciones de Código
* **Python:** Cumplimiento de **PEP 8**.
* **Commits:** Uso de **Conventional Commits**.
* **Documentación:** Docstrings redactados en **inglés**.

### 📄 Licencia
© 2026 Universidad Central del Ecuador - Facultad de Ingeniería y Ciencias Aplicadas

*Proyecto académico para fines educativos.*


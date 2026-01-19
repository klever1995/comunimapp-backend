from dotenv import load_dotenv
from datetime import datetime
from firebase_admin import messaging
import os

# Configuración de Firebase desde variables de entorno
load_dotenv()

firebase_credentials = {
    "type": os.getenv("FIREBASE_TYPE"),
    "project_id": os.getenv("FIREBASE_PROJECT_ID"),
    "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID"),
    "private_key": os.getenv("FIREBASE_PRIVATE_KEY").replace("\\n", "\n"),
    "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
    "client_id": os.getenv("FIREBASE_CLIENT_ID"),
    "auth_uri": os.getenv("FIREBASE_AUTH_URI"),
    "token_uri": os.getenv("FIREBASE_TOKEN_URI"),
    "auth_provider_x509_cert_url": os.getenv("FIREBASE_AUTH_PROVIDER_X509_CERT_URL"),
    "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_X509_CERT_URL"),
    "universe_domain": os.getenv("FIREBASE_UNIVERSE_DOMAIN")
}

# Inicialización de Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, firestore, auth

if not firebase_admin._apps:
    try:
        cred = credentials.Certificate(firebase_credentials)
        firebase_app = firebase_admin.initialize_app(cred)
        print("Conexión a Firebase exitosa.")
    except Exception as e:
        print("Error al conectar con Firebase:", e)
        raise e

# Clientes de Firestore y Authentication
db = firestore.client()
auth = auth  

# Función para enviar notificaciones push mediante Firebase Cloud Messaging
def send_push_notification(fcm_token: str, title: str, body: str, data: dict = None) -> dict:
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            token=fcm_token,
            data=data if data else {},
        )
        
        response = messaging.send(message)
        print(f"Notificación enviada exitosamente. Message ID: {response}")
        return {"success": True, "message_id": response}
    
    except messaging.UnregisteredError:
        print(f"Token FCM no registrado: {fcm_token}")
        return {"success": False, "error": "Token no registrado"}
    
    except messaging.InvalidArgumentError as e:
        print(f"Token FCM inválido: {e}")
        return {"success": False, "error": f"Token inválido: {str(e)}"}
    
    except Exception as e:
        print(f"Error enviando notificación: {e}")
        return {"success": False, "error": str(e)}

# Función auxiliar para obtener tokens FCM activos de un usuario
def get_user_fcm_tokens(user_id: str) -> list:
    try:
        tokens_ref = db.collection("fcm_tokens")
        query = tokens_ref.where("user_id", "==", user_id).where("is_active", "==", True).stream()
        
        tokens = []
        for doc in query:
            token_data = doc.to_dict()
            tokens.append(token_data.get("fcm_token"))
        
        print(f"Encontrados {len(tokens)} tokens para usuario {user_id}")
        return tokens
    
    except Exception as e:
        print(f"Error obteniendo tokens FCM: {e}")
        return []

# Función de prueba para notificar al usuario cuando crea un reporte
def notify_self_on_report(user_id: str, report_title: str = "Reporte de prueba"):
    tokens = get_user_fcm_tokens(user_id)
    
    if not tokens:
        print(f"Usuario {user_id} no tiene tokens FCM registrados.")
        return
    
    fcm_token = tokens[0]
    
    result = send_push_notification(
        fcm_token=fcm_token,
        title="¡Reporte creado!",
        body=f"Has creado el reporte: '{report_title}'",
        data={
            "type": "report_created",
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            "test": "true"
        }
    )
    
    if result.get("success"):
        print(f"Notificación de prueba enviada a {user_id}")
    else:
        print(f"Notificación de prueba falló: {result.get('error')}")
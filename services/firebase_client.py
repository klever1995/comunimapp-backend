from dotenv import load_dotenv
import os

# Cargar el archivo .env
load_dotenv()

# Usar las variables de entorno
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

# Inicializa Firebase
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

# Cliente de Firestore
db = firestore.client()

# Cliente de Firebase Authentication (exportarlo)
auth = auth  # Esto exporta el módulo auth de firebase_admin
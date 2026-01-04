import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))


def send_email(to_email: str, subject: str, body: str):
    """
    Envía un correo electrónico usando SMTP.
    :param to_email: destinatario
    :param subject: asunto del correo
    :param body: contenido HTML o texto
    """
    msg = EmailMessage()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body, subtype="html")  # podemos usar HTML para mejor formato

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
            smtp.starttls()  # cifrado TLS
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print(f"Correo enviado a {to_email}")
    except Exception as e:
        print(f"No se pudo enviar el correo a {to_email}: {e}")
        raise e

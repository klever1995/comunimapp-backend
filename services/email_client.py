import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv

# Carga variables de entorno desde .env (solo para desarrollo local)
load_dotenv()

# Variables de entorno
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = os.getenv("EMAIL_ADDRESS")  # el correo que usas para enviar

def send_email(to_email: str, subject: str, body: str):

    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=to_email,
        subject=subject,
        html_content=body
    )

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"Email enviado a {to_email} - status {response.status_code}")
    except Exception as e:
        print(f"Error enviando email a {to_email}: {e}")
        raise e

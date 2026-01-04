from services.email_client import send_email

# Dirección de destino (puedes usar tu propio correo para pruebas)
destinatario = "klever_mix@hotmail.com"
asunto = "Prueba de correo - SmartFitness"
cuerpo = """
<h2>¡Hola!</h2>
<p>Este es un correo de prueba enviado desde el backend de SmartFitness.</p>
<p>Si lo recibes, significa que el cliente de correo funciona correctamente.</p>
"""

try:
    send_email(to_email=destinatario, subject=asunto, body=cuerpo)
    print("Correo de prueba enviado correctamente.")
except Exception as e:
    print("Error al enviar el correo:", e)

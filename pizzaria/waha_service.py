import os
import base64
import mimetypes
import requests
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MEDIA_ROOT = os.environ.get('MEDIA_ROOT', '/app/media')

WAHA_URL = os.environ.get('WAHA_URL', 'http://localhost:3000')
WAHA_SESSION = os.environ.get('WAHA_SESSION', 'default')
WAHA_API_KEY = os.environ.get('WAHA_API_KEY', 'pizzaria-api-key-123')

def get_headers():
    """Retorna headers com autenticacao WAHA."""
    return {
        'Content-Type': 'application/json',
        'X-Api-Key': WAHA_API_KEY
    }


def format_phone(phone: str) -> str:
    """Formata o telefone para o formato do WhatsApp."""
    phone = ''.join(filter(str.isdigit, phone))
    if not phone.startswith('55'):
        phone = '55' + phone
    return f"{phone}@c.us"


def send_whatsapp_message(phone: str, message: str) -> bool:
    """Envia mensagem de texto via WAHA."""
    try:
        url = f"{WAHA_URL}/api/sendText"
        payload = {
            "chatId": format_phone(phone),
            "text": message,
            "session": WAHA_SESSION
        }
        response = requests.post(url, json=payload, headers=get_headers(), timeout=30)
        response.raise_for_status()
        logger.info(f"Mensagem enviada para {phone}")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar mensagem para {phone}: {e}")
        return False


def send_whatsapp_image(phone: str, image_path: str, caption: str = "") -> bool:
    """Envia imagem via WAHA usando base64."""
    try:
        # Converte path relativo para absoluto
        if image_path.startswith('/media/'):
            file_path = Path(MEDIA_ROOT) / image_path.replace('/media/', '')
        elif image_path.startswith('media/'):
            file_path = Path(MEDIA_ROOT) / image_path.replace('media/', '')
        else:
            file_path = Path(MEDIA_ROOT) / image_path

        if not file_path.exists():
            logger.error(f"Arquivo de imagem nao encontrado: {file_path}")
            return False

        # Lê e converte para base64
        with open(file_path, 'rb') as f:
            image_data = base64.b64encode(f.read()).decode('utf-8')

        # Detecta mimetype
        mimetype, _ = mimetypes.guess_type(str(file_path))
        if not mimetype:
            mimetype = 'image/jpeg'

        url = f"{WAHA_URL}/api/sendImage"
        payload = {
            "chatId": format_phone(phone),
            "file": {
                "mimetype": mimetype,
                "data": f"data:{mimetype};base64,{image_data}"
            },
            "caption": caption,
            "session": WAHA_SESSION
        }
        logger.info(f"Enviando imagem para {phone}: {file_path}")
        response = requests.post(url, json=payload, headers=get_headers(), timeout=60)

        if response.status_code != 200:
            logger.error(f"WAHA erro {response.status_code}: {response.text}")

        response.raise_for_status()
        logger.info(f"Imagem enviada para {phone}")
        return True
    except Exception as e:
        logger.error(f"Erro ao enviar imagem para {phone}: {e}")
        return False


def get_session_status() -> dict:
    """Verifica status da sessao WAHA."""
    try:
        url = f"{WAHA_URL}/api/sessions/{WAHA_SESSION}"
        response = requests.get(url, headers=get_headers(), timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"Erro ao verificar status da sessao: {e}")
        return {"status": "error", "message": str(e)}

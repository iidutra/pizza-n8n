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


def is_valid_phone(phone: str) -> bool:
    """Verifica se é um número de telefone válido (não um LID)."""
    if not phone:
        return False
    # Remove não-dígitos
    digits = ''.join(filter(str.isdigit, phone))
    # Telefone brasileiro válido: 10-13 dígitos (com ou sem DDI 55)
    # LIDs são muito longos (15+ dígitos) ou não começam com padrão brasileiro
    if len(digits) < 10 or len(digits) > 13:
        return False
    # Se começa com 55, verifica o DDD (2 dígitos após 55)
    if digits.startswith('55'):
        ddd = digits[2:4]
        # DDDs válidos do Brasil: 11-99
        if not (11 <= int(ddd) <= 99):
            return False
    return True


def format_phone(phone: str) -> str:
    """Formata o telefone para o formato do WhatsApp."""
    phone = ''.join(filter(str.isdigit, phone))
    if not phone.startswith('55'):
        phone = '55' + phone
    return f"{phone}@c.us"


def send_whatsapp_message(phone: str, message: str) -> bool:
    """Envia mensagem de texto via WAHA."""
    try:
        # Valida se é um número de telefone real
        if not is_valid_phone(phone):
            logger.warning(f"Numero invalido ignorado (provavelmente LID): {phone}")
            return False

        chat_id = format_phone(phone)

        # Tenta múltiplos endpoints do WAHA (diferentes versões)
        endpoints = [
            f"{WAHA_URL}/api/sendText",  # WAHA Plus / Core
            f"{WAHA_URL}/api/{WAHA_SESSION}/sendText",  # Formato alternativo
        ]

        payload_base = {
            "chatId": chat_id,
            "text": message,
            "session": WAHA_SESSION
        }

        for url in endpoints:
            try:
                logger.info(f"Tentando enviar para {chat_id} via {url}")
                response = requests.post(url, json=payload_base, headers=get_headers(), timeout=30)

                if response.status_code in [200, 201]:
                    logger.info(f"Mensagem enviada para {phone} via {url}")
                    return True
                else:
                    logger.warning(f"Falha em {url}: {response.status_code} - {response.text[:200]}")
            except Exception as e:
                logger.warning(f"Erro em {url}: {e}")
                continue

        logger.error(f"Todas as tentativas falharam para {phone}")
        return False

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

        chat_id = format_phone(phone)

        # Formato da API WAHA v2024+
        url = f"{WAHA_URL}/api/{WAHA_SESSION}/sendImage"
        payload = {
            "chatId": chat_id,
            "file": {
                "mimetype": mimetype,
                "data": f"data:{mimetype};base64,{image_data}"
            },
            "caption": caption
        }

        logger.info(f"Enviando imagem para {phone}: {file_path}")
        response = requests.post(url, json=payload, headers=get_headers(), timeout=60)

        if response.status_code not in [200, 201]:
            # Tenta formato antigo da API
            logger.warning(f"Tentando formato antigo da API WAHA para imagem...")
            url = f"{WAHA_URL}/api/sendImage"
            payload["session"] = WAHA_SESSION
            response = requests.post(url, json=payload, headers=get_headers(), timeout=60)

        if response.status_code in [200, 201]:
            logger.info(f"Imagem enviada para {phone}")
            return True
        else:
            logger.error(f"WAHA erro {response.status_code}: {response.text}")
            return False

    except Exception as e:
        logger.error(f"Erro ao enviar imagem para {phone}: {e}")
        return False


def get_session_status() -> dict:
    """Verifica status da sessao WAHA."""
    try:
        # Tenta formato novo da API
        url = f"{WAHA_URL}/api/{WAHA_SESSION}"
        response = requests.get(url, headers=get_headers(), timeout=10)

        if response.status_code == 404:
            # Tenta formato antigo
            url = f"{WAHA_URL}/api/sessions/{WAHA_SESSION}"
            response = requests.get(url, headers=get_headers(), timeout=10)

        return response.json()
    except Exception as e:
        logger.error(f"Erro ao verificar status da sessao: {e}")
        return {"status": "error", "message": str(e)}


def start_session() -> dict:
    """Inicia sessao WAHA se nao estiver ativa."""
    try:
        url = f"{WAHA_URL}/api/{WAHA_SESSION}/start"
        response = requests.post(url, json={}, headers=get_headers(), timeout=30)

        if response.status_code == 404:
            # Tenta formato antigo
            url = f"{WAHA_URL}/api/sessions/start"
            payload = {"name": WAHA_SESSION}
            response = requests.post(url, json=payload, headers=get_headers(), timeout=30)

        return response.json()
    except Exception as e:
        logger.error(f"Erro ao iniciar sessao: {e}")
        return {"status": "error", "message": str(e)}

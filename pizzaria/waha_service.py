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


def is_valid_chat_id(chat_id: str) -> bool:
    """Verifica se é um chat_id válido (telefone ou LID)."""
    if not chat_id:
        return False

    # Aceita LIDs (@lid)
    if '@lid' in chat_id.lower():
        return True

    # Aceita formato completo (@c.us ou @s.whatsapp.net)
    if '@c.us' in chat_id or '@s.whatsapp.net' in chat_id:
        return True

    # Remove não-dígitos para validar número
    digits = ''.join(filter(str.isdigit, chat_id))

    # Aceita números com 8-18 dígitos (cobre telefones e LIDs numéricos)
    if len(digits) >= 8:
        return True

    return False


def format_chat_id(chat_id: str) -> str:
    """Formata o chat_id para o formato do WhatsApp."""
    # Se já está no formato correto, retorna como está
    if '@lid' in chat_id.lower():
        return chat_id
    if '@c.us' in chat_id:
        return chat_id
    if '@s.whatsapp.net' in chat_id:
        return chat_id.replace('@s.whatsapp.net', '@c.us')

    # Remove não-dígitos
    phone = ''.join(filter(str.isdigit, chat_id))

    # Adiciona 55 se for telefone brasileiro (não LID)
    if len(phone) <= 13 and not phone.startswith('55'):
        phone = '55' + phone

    return f"{phone}@c.us"


# Mantém compatibilidade com código antigo
def is_valid_phone(phone: str) -> bool:
    """Alias para is_valid_chat_id - mantido para compatibilidade."""
    return is_valid_chat_id(phone)


def format_phone(phone: str) -> str:
    """Alias para format_chat_id - mantido para compatibilidade."""
    return format_chat_id(phone)


def send_whatsapp_buttons(phone: str, body: str, buttons: list[str]) -> bool:
    """Envia mensagem com botões de resposta rápida (fallback para texto)."""
    if not buttons:
        return send_whatsapp_message(phone, body)

    try:
        if not is_valid_chat_id(phone):
            return False
        chat_id = format_chat_id(phone)
        labels = buttons[:3]
        endpoints = [
            (f"{WAHA_URL}/api/sendButtons", {
                "session": WAHA_SESSION,
                "chatId": chat_id,
                "headerText": "",
                "body": body,
                "footerText": "",
                "buttons": [{"type": "reply", "id": str(i), "text": label} for i, label in enumerate(labels)],
            }),
            (f"{WAHA_URL}/api/{WAHA_SESSION}/sendButtons", {
                "chatId": chat_id,
                "text": body,
                "buttons": labels,
            }),
        ]
        for url, payload in endpoints:
            try:
                response = requests.post(url, json=payload, headers=get_headers(), timeout=30)
                if response.status_code in (200, 201):
                    logger.info(f"Botoes enviados para {phone}")
                    return True
            except Exception as e:
                logger.warning(f"sendButtons falhou em {url}: {e}")
    except Exception as e:
        logger.warning(f"send_whatsapp_buttons: {e}")

    fallback = body + "\n\n" + " | ".join(f"*{b}*" for b in buttons[:3])
    return send_whatsapp_message(phone, fallback)


def send_whatsapp_message(phone: str, message: str) -> bool:
    """Envia mensagem de texto via WAHA. Aceita telefone ou LID."""
    try:
        # Valida se é um chat_id válido (telefone ou LID)
        if not is_valid_chat_id(phone):
            logger.warning(f"Chat ID invalido: {phone}")
            return False

        chat_id = format_chat_id(phone)

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

        chat_id = format_chat_id(phone)

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

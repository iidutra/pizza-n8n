"""Transcrição de áudio via Groq Whisper (fallback quando WAHA envia direto ao Django)."""
import logging
import os
import re

import requests

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
WHISPER_MODEL = os.environ.get('GROQ_WHISPER_MODEL', 'whisper-large-v3-turbo')
WHISPER_URL = 'https://api.groq.com/openai/v1/audio/transcriptions'


def _waha_headers():
    from .waha_service import WAHA_API_KEY
    return {'X-Api-Key': WAHA_API_KEY}


def _fix_media_url(media_url: str) -> str:
    from .waha_service import WAHA_URL
    if not media_url:
        return media_url
    for host in ('localhost:3000', '127.0.0.1:3000', 'waha:3000'):
        if host in media_url:
            waha_host = WAHA_URL.replace('http://', '').replace('https://', '')
            return media_url.replace(f'http://{host}', WAHA_URL).replace(f'https://{host}', WAHA_URL).replace(host, waha_host)
    if media_url.startswith('/'):
        return f"{WAHA_URL.rstrip('/')}{media_url}"
    return media_url


def download_audio_from_payload(payload: dict) -> bytes | None:
    """Baixa bytes do áudio a partir do payload WAHA."""
    from .waha_service import WAHA_URL, WAHA_SESSION

    media = payload.get('media') or {}
    candidates = [
        media.get('url'),
        payload.get('mediaUrl'),
        (payload.get('_data') or {}).get('media', {}).get('url'),
        media.get('link'),
    ]

    for url in candidates:
        if not url:
            continue
        fixed = _fix_media_url(url)
        try:
            response = requests.get(fixed, headers=_waha_headers(), timeout=30)
            if response.status_code == 200 and response.content:
                return response.content
        except Exception as exc:
            logger.warning('Falha ao baixar áudio via URL %s: %s', fixed, exc)

    message_id = payload.get('id') or (payload.get('_data') or {}).get('Info', {}).get('ID')
    chat_id = payload.get('from') or payload.get('chatId')
    if message_id and chat_id:
        endpoints = [
            f"{WAHA_URL}/api/{WAHA_SESSION}/messages/{message_id}/download",
            f"{WAHA_URL}/api/{WAHA_SESSION}/chats/{chat_id}/messages/{message_id}?download=true",
        ]
        for endpoint in endpoints:
            try:
                response = requests.get(endpoint, headers=_waha_headers(), timeout=30)
                if response.status_code == 200 and response.content:
                    return response.content
            except Exception as exc:
                logger.warning('Falha ao baixar áudio via %s: %s', endpoint, exc)

    return None


def transcribe_audio(audio_bytes: bytes, filename: str = 'audio.ogg') -> dict:
    """
    Transcreve áudio com Groq Whisper.
    Retorna {'success': bool, 'text': str, 'error': str|None}.
    """
    if not GROQ_API_KEY or GROQ_API_KEY.startswith('your_'):
        return {'success': False, 'text': '', 'error': 'GROQ_API_KEY não configurada'}

    if not audio_bytes:
        return {'success': False, 'text': '', 'error': 'Áudio vazio'}

    try:
        response = requests.post(
            WHISPER_URL,
            headers={'Authorization': f'Bearer {GROQ_API_KEY}'},
            files={'file': (filename, audio_bytes, 'audio/ogg')},
            data={
                'model': WHISPER_MODEL,
                'language': 'pt',
                'response_format': 'json',
                'temperature': 0,
            },
            timeout=30,
        )
        if response.status_code != 200:
            logger.error('Groq Whisper erro %s: %s', response.status_code, response.text[:300])
            return {'success': False, 'text': '', 'error': f'whisper_http_{response.status_code}'}

        text = (response.json().get('text') or '').strip()
        text = re.sub(r'\s+', ' ', text)
        if not text:
            return {'success': False, 'text': '', 'error': 'transcricao_vazia'}
        return {'success': True, 'text': text, 'error': None}
    except Exception as exc:
        logger.exception('Erro na transcrição Groq Whisper')
        return {'success': False, 'text': '', 'error': str(exc)}


def transcribe_waha_payload(payload: dict) -> dict:
    """Baixa e transcreve áudio de um payload WAHA."""
    audio_bytes = download_audio_from_payload(payload)
    if not audio_bytes:
        return {'success': False, 'text': '', 'error': 'download_failed'}
    return transcribe_audio(audio_bytes)

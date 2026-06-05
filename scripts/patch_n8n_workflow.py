"""Atualiza n8n_workflow_hybrid_bot.json com STT de áudio e buffer de 3s."""
import json
from pathlib import Path

WORKFLOW_PATH = Path(__file__).resolve().parent.parent / 'n8n_workflow_hybrid_bot.json'

NORMALIZE_SUFFIX = """
const AUDIO_TYPES = ['ptt', 'audio', 'voice', 'audio_message'];
const isAudio = AUDIO_TYPES.includes((msgType || '').toLowerCase());

if (!text && !isAudio) {
  return [{ json: { skip: true, reason: 'empty_message' } }];
}

return [{
  json: {
    skip: false,
    is_lid: isLid,
    normalized: {
      channel: 'whatsapp',
      phone: chatId,
      chat_id: chatId,
      text: text,
      message_id: messageId,
      timestamp: timestamp || currentTime,
      msg_type: msgType,
      customer_name: customerName,
      is_audio: isAudio
    },
    _raw: body
  }
}];"""

STT_CODE = r"""// TRANSCRIÇÃO DE ÁUDIO (Groq Whisper)
const data = $input.first().json;
const AUDIO_TYPES = ['ptt', 'audio', 'voice', 'audio_message'];
const msgType = (data.normalized?.msg_type || '').toLowerCase();
const isAudio = data.normalized?.is_audio || AUDIO_TYPES.includes(msgType);

if (!isAudio) {
  return [{ json: data }];
}

const GROQ_API_KEY = $env.GROQ_API_KEY;
const WAHA_URL = ($env.WAHA_URL || 'http://waha:3000').replace(/\/$/, '');
const WAHA_API_KEY = $env.WAHA_API_KEY || '';
const WAHA_SESSION = $env.WAHA_SESSION || 'default';
const chatId = data.normalized.chat_id;
const messageId = data.normalized.message_id;
const payload = data._raw?.payload || {};
const wahaHeaders = { 'Content-Type': 'application/json', 'X-Api-Key': WAHA_API_KEY };

try {
  await this.helpers.httpRequest({
    method: 'POST',
    url: `${WAHA_URL}/api/sendText`,
    headers: wahaHeaders,
    body: { session: WAHA_SESSION, chatId, text: 'Recebi seu áudio! Só um instante 🎧' },
    json: true,
  });
} catch (e) {}

function fixMediaUrl(url) {
  if (!url) return url;
  return url.replace('http://localhost:3000', WAHA_URL).replace('http://127.0.0.1:3000', WAHA_URL).replace('http://waha:3000', WAHA_URL);
}

let audioBuffer = null;
for (const candidate of [payload.media?.url, payload.mediaUrl, payload._data?.media?.url, payload.media?.link]) {
  if (!candidate || audioBuffer) continue;
  try {
    audioBuffer = await this.helpers.httpRequest({
      method: 'GET', url: fixMediaUrl(candidate), headers: { 'X-Api-Key': WAHA_API_KEY }, encoding: 'arraybuffer',
    });
  } catch (e) {}
}

if (!audioBuffer) {
  for (const url of [
    `${WAHA_URL}/api/${WAHA_SESSION}/messages/${messageId}/download`,
    `${WAHA_URL}/api/${WAHA_SESSION}/chats/${encodeURIComponent(chatId)}/messages/${messageId}?download=true`,
  ]) {
    try {
      audioBuffer = await this.helpers.httpRequest({
        method: 'GET', url, headers: { 'X-Api-Key': WAHA_API_KEY }, encoding: 'arraybuffer',
      });
      if (audioBuffer) break;
    } catch (e) {}
  }
}

let transcript = '';
let transcriptionError = null;

if (!GROQ_API_KEY || GROQ_API_KEY.startsWith('your_')) {
  transcriptionError = 'GROQ_API_KEY_missing';
} else if (!audioBuffer) {
  transcriptionError = 'audio_download_failed';
} else {
  try {
    const FormData = require('form-data');
    const form = new FormData();
    form.append('file', Buffer.from(audioBuffer), { filename: 'audio.ogg', contentType: 'audio/ogg' });
    form.append('model', 'whisper-large-v3-turbo');
    form.append('language', 'pt');
    form.append('response_format', 'json');
    form.append('temperature', '0');
    const whisperResponse = await this.helpers.httpRequest({
      method: 'POST',
      url: 'https://api.groq.com/openai/v1/audio/transcriptions',
      headers: { Authorization: `Bearer ${GROQ_API_KEY}`, ...form.getHeaders() },
      body: form,
    });
    transcript = (whisperResponse.text || '').trim();
    if (!transcript) transcriptionError = 'empty_transcription';
  } catch (e) {
    transcriptionError = e.message || 'whisper_error';
  }
}

if (!transcript) {
  try {
    await this.helpers.httpRequest({
      method: 'POST',
      url: `${WAHA_URL}/api/sendText`,
      headers: wahaHeaders,
      body: {
        session: WAHA_SESSION,
        chatId,
        text: 'Não consegui entender o áudio 😅\n\nTenta de novo ou escreve: "2 calabresa entrega aponia"',
      },
      json: true,
    });
  } catch (e) {}
  return [{ json: { skip: true, reason: transcriptionError || 'transcription_failed' } }];
}

return [{
  json: {
    ...data,
    normalized: {
      ...data.normalized,
      text: transcript,
      msg_type: 'chat',
      was_audio: true,
      original_msg_type: msgType,
    },
    transcription: {
      provider: 'groq',
      model: 'whisper-large-v3-turbo',
      text: transcript,
      success: true,
    },
  },
}];"""


def patch_normalize_code(code: str) -> str:
    old_tail = "// Ignora mensagens vazias (exceto se for mídia)\nif (!text && msgType === 'chat') {\n  return [{ json: { skip: true, reason: 'empty_message' } }];\n}\n\n// Retorna dados normalizados - usa chat_id completo como identificador\nreturn [{\n  json: {\n    skip: false,\n    is_lid: isLid,\n    normalized: {\n      channel: 'whatsapp',\n      phone: chatId,\n      chat_id: chatId,\n      text: text,\n      message_id: messageId,\n      timestamp: timestamp || currentTime,\n      msg_type: msgType,\n      customer_name: customerName\n    },\n    _raw: body\n  }\n}];"
    if old_tail not in code:
        raise RuntimeError('Normalize node tail not found')
    return code.replace(old_tail, NORMALIZE_SUFFIX.strip())


def patch_router_code(code: str) -> str:
    code = code.replace('const needsLLM =', 'let needsLLM =', 1)
    anchor = "\n\nlet reason = 'safe_pattern';"
    if anchor not in code:
        raise RuntimeError('Router anchor not found')
    insert = (
        "\n\nif (data.normalized?.was_audio && text.length > 1) {\n"
        "  needsLLM = true;\n"
        "}\n\nlet reason = 'safe_pattern';"
    )
    code = code.replace(anchor, insert, 1)
    return code.replace(
        "if (messagesCount > 1) reason = 'multi_message';",
        "if (messagesCount > 1) reason = 'multi_message';\n"
        "  else if (data.normalized?.was_audio) reason = 'audio_transcription';",
        1,
    )


def patch_envelope_code(code: str) -> str:
    if 'transcription:' in code:
        return code
    return code.replace(
        '  address_resolution: data.address_resolution || {',
        "  transcription: data.transcription || null,\n  address_resolution: data.address_resolution || {",
    )


def main():
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding='utf-8'))

    for node in workflow['nodes']:
        name = node.get('name')
        if name == 'Normalizar Mensagem':
            node['parameters']['jsCode'] = patch_normalize_code(node['parameters']['jsCode'])
        elif name == 'Aguardar Buffer':
            node['parameters']['amount'] = 3
        elif name == 'Router Rules-First':
            node['parameters']['jsCode'] = patch_router_code(node['parameters']['jsCode'])
        elif name in ('Montar Envelope (LLM)', 'Montar Envelope (No LLM)'):
            node['parameters']['jsCode'] = patch_envelope_code(node['parameters']['jsCode'])
        elif name == 'Chamar Claude Haiku':
            body = node['parameters']['jsonBody']
            extra = (
                "\\n11. Aceite erros de digitação e linguagem oral (klabresa, qro, duas de calabresa)\\n"
                "12. Áudio transcrito pode ter palavras imprecisas — use o cardápio como referência"
            )
            if '11. Aceite erros' not in body:
                node['parameters']['jsonBody'] = body.replace(
                    '10. Se pedir múltiplas pizzas',
                    f'{extra}\\n10. Se pedir múltiplas pizzas',
                )

    if not any(n.get('name') == 'Processar Audio STT' for n in workflow['nodes']):
        workflow['nodes'].append({
            'parameters': {'jsCode': STT_CODE},
            'id': 'code-audio-stt',
            'name': 'Processar Audio STT',
            'type': 'n8n-nodes-base.code',
            'typeVersion': 2,
            'position': [750, 260],
        })

    workflow['connections']['Mensagem Valida?'] = {
        'main': [
            [{'node': 'Processar Audio STT', 'type': 'main', 'index': 0}],
            [{'node': 'Ignorar', 'type': 'main', 'index': 0}],
        ]
    }
    workflow['connections']['Processar Audio STT'] = {
        'main': [[{'node': 'Buffer Mensagens', 'type': 'main', 'index': 0}]]
    }

    WORKFLOW_PATH.write_text(json.dumps(workflow, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'Workflow atualizado: {WORKFLOW_PATH}')


if __name__ == '__main__':
    main()

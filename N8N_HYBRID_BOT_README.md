# Workflow n8n Hybrid Bot - Pizzaria

## Arquivos Criados/Modificados

| Arquivo | Descrição |
|---------|-----------|
| `n8n_workflow_hybrid_bot.json` | Workflow n8n completo (importar) — **STT + LLM** |
| `pizzaria/bot_views.py` | Bot conversacional, confirmação de pedido, áudio |
| `pizzaria/audio_service.py` | Transcrição Groq Whisper (fallback Django) |
| `pizzaria/conversational_helpers.py` | Welcome, ajuda, rascunho, detector de confusão |
| `pizzaria/views.py` | Endpoints `/api/n8n/neighborhoods/` e `/api/n8n/products/` |
| `pizzaria/urls.py` | Rotas para os novos endpoints |
| `ATENDIMENTO_CONVERSACIONAL.md` | Documentação do atendimento conversacional |

## Arquitetura

```
WAHA → Webhook → Normalizar → [Áudio? STT Whisper] → Buffer (3s) → Router → [LLM?] → Django
                                          │
                                          ├─ SIM: Bairros + Cardápio → Claude Haiku → Match Bairro → Envelope → Django
                                          │
                                          └─ NÃO: Envelope simples → Django
```

## Variáveis de Ambiente

Configure no n8n (Settings > Environment Variables ou docker-compose):

```bash
# Anthropic (obrigatório) — LLM Claude Haiku
ANTHROPIC_API_KEY=sk-ant-xxxxx
ANTHROPIC_LLM_MODEL=claude-haiku-4-5

# Groq (obrigatório) — Whisper STT para áudio
GROQ_API_KEY=gsk_xxxxx

# WAHA (obrigatório para transcrição de áudio)
WAHA_URL=http://waha:3000
WAHA_API_KEY=sua-api-key
WAHA_SESSION=default

# Backend (opcional — URLs nos nodes HTTP)
BACKEND_URL=http://web:8000
```

## Endpoints Django Necessários

### 1. `/api/delivery-fees/` (já existe)

```bash
GET http://web:8000/api/delivery-fees/
```

Resposta:
```json
[
  {"id": 1, "neighborhood": "Planalto", "fee": "12.00", "estimated_time": 60, "active": true},
  {"id": 2, "neighborhood": "Aponia", "fee": "6.00", "estimated_time": 45, "active": true}
]
```

### 2. `/api/products/` (já existe)

```bash
GET http://web:8000/api/products/?active_only=true
```

### 3. `/api/bot/message/` (precisa atualização)

O Django precisa processar o novo envelope:

```json
{
  "source": "n8n",
  "normalized": {
    "channel": "whatsapp",
    "phone": "5569993639552",
    "chat_id": "5569993639552@c.us",
    "text": "Henrique soro 6225 aponia",
    "message_id": "3EB0ABC123",
    "timestamp": 1706889600,
    "msg_type": "chat",
    "customer_name": "Igor"
  },
  "buffer": {
    "combined_text": "2 pizza gg / calabre e quatro queijo",
    "messages_count": 2,
    "window_seconds": 10
  },
  "routing": {
    "used_llm": true,
    "reason": "multi_message"
  },
  "llm": {
    "provider": "anthropic",
    "model": "claude-haiku-4-5",
    "valid": true,
    "validation_error": null,
    "result": { ... }
  },
  "address_resolution": {
    "neighborhood_input": "aponia",
    "matched_neighborhood": "Aponia",
    "match_score": 95,
    "delivery_fee": 6.0,
    "candidates": [...]
  }
}
```

## Como Testar

### 1. Mensagem padrão (sem LLM)

```
Mensagem: "1"
Esperado: routing.used_llm = false, reason = "safe_pattern"
```

```
Mensagem: "pix"
Esperado: routing.used_llm = false
```

### 2. Pedido em texto livre (com LLM)

```
Mensagem: "4 queijo tbm"
Esperado:
- routing.used_llm = true
- llm.result.intent = "add_item"
- llm.result.entities.order.items = [{ name: "4 Queijos", quantity: 1 }]
```

### 3. Múltiplas mensagens (buffer)

Envie rapidamente (< 10s entre elas):
```
Mensagem 1: "2 pizza gg"
Mensagem 2: "calabre e quatro queijo"
Mensagem 3: "e a outra"
Mensagem 4: "baiana e frango com cheddar"
```

Esperado:
```json
{
  "buffer": {
    "combined_text": "2 pizza gg / calabre e quatro queijo / e a outra / baiana e frango com cheddar",
    "messages_count": 4
  },
  "routing": { "used_llm": true, "reason": "multi_message" }
}
```

### 4. Endereço com bairro

```
Mensagem: "Henrique soro 6225 aponia"
Esperado:
- llm.result.intent = "provide_address"
- llm.result.entities.address.address_line = "Henrique soro"
- llm.result.entities.address.number = "6225"
- llm.result.entities.address.neighborhood_text = "aponia"
- address_resolution.matched_neighborhood = "Aponia"
- address_resolution.match_score >= 90
- address_resolution.delivery_fee = 6.0
```

### 5. Troco após pergunta

```
Mensagem: "100"
(após "precisa de troco?")
Esperado: routing.used_llm = false (é número simples)
```

### 6. Áudio (STT)

Envie um áudio: *"quero duas calabresa entrega aponia"*

Esperado:
- Resposta imediata: "Recebi seu áudio! Só um instante 🎧"
- `transcription.success = true` no envelope
- `routing.reason = "audio_transcription"`
- Bot anota o pedido ou pede confirmação

### 7. Pedido completo (confirmação)

Mensagem: *"2 calabresa henrique soares 6225 aponia pix"*

Esperado:
- Resumo do pedido + "Tá certo? Responde SIM"
- Estado Django: `awaiting_draft_confirmation`

## Regras do Router

### Padrões SAFE (não usa LLM):

- Números simples: `1`, `2`, `15`
- Confirmações: `sim`, `não`, `ok`, `beleza`
- Pagamento: `pix`, `dinheiro`, `cartão`
- Entrega: `entrega`, `retirada`
- Valores: `R$ 100`, `50`
- Comandos: `voltar`, `cancelar`, `menu`
- Saudações simples: `oi`, `olá`

### Padrões que USAM LLM:

- **Áudio transcrito** (sempre)
- Múltiplas mensagens (buffer > 1)
- Texto com sabores de pizza
- Endereços (rua, número, bairro)
- Modificadores (`sem`, `tirar`, `extra`)
- Gírias (`tbm`, `outra`, `mais uma`)
- Meio a meio (`meio`, `metade`)
- Mais de 3 palavras

## Match de Bairro

### Regras:

| Score | Ação |
|-------|------|
| >= 90 | Aceita automaticamente, inclui `delivery_fee` |
| 75-89 | Envia `candidates` para Django confirmar com cliente |
| < 75  | Django deve pedir bairro novamente |

### Exemplos:

```
Input: "aponia" → Match: "Aponia" (score: 100) → delivery_fee: 6.0
Input: "Aponiã" → Match: "Aponia" (score: 95) → delivery_fee: 6.0
Input: "planalto norte" → Match: "Planalto" (score: 85) → needs_confirmation
Input: "xyz123" → Match: null (score: 30) → not_found
```

## Importar no n8n

1. Acesse o n8n: http://localhost:5678
2. Vá em **Workflows** > **Import from file**
3. Selecione `n8n_workflow_hybrid_bot.json`
4. Configure as credenciais (Anthropic API Key)
5. Ative o workflow

## Desativar Workflow Antigo

Após testar, desative o workflow `n8n_workflow_pizzaria.json` para evitar duplicação.

## Troubleshooting

### Erro "ANTHROPIC_API_KEY not found"

Configure a variável de ambiente no n8n:
- Settings > Environment Variables (ou `.env` + docker-compose)
- Adicione `ANTHROPIC_API_KEY`

Para obter a key:
1. Acesse https://console.anthropic.com/settings/keys
2. Crie uma API key

### Erro "GROQ_API_KEY not found" (áudio)

Para transcrição Whisper, ainda é necessário Groq:
- Adicione `GROQ_API_KEY` no n8n
- Obtenha em https://console.groq.com → API Keys

### Buffer não funciona

O buffer usa `staticData` do n8n (em memória). Janela atual: **3 segundos**. Para produção com múltiplas instâncias, substitua pelo Redis node.

### Áudio não transcreve

- Verifique `GROQ_API_KEY`, `WAHA_URL` e `WAHA_API_KEY` no n8n
- Confirme que o node `Processar Audio STT` está no fluxo (entre "Mensagem Valida?" e "Buffer Mensagens")
- Veja [ATENDIMENTO_CONVERSACIONAL.md](ATENDIMENTO_CONVERSACIONAL.md)

### LLM retorna JSON inválido

O node "Parse LLM Response" tenta limpar markdown e fazer parse. Se falhar:
- `llm.valid = false`
- `llm.validation_error = "json_parse_error: ..."`
- Django deve usar fallback (menu guiado)

### Match de bairro muito amplo

Ajuste os thresholds no node "Match Bairro Fuzzy":
- Linha com `score >= 90`: aumentar para 95
- Linha com `score >= 75`: aumentar para 80

# Workflow n8n Hybrid Bot - Pizzaria

## Arquivos Criados/Modificados

| Arquivo | Descrição |
|---------|-----------|
| `n8n_workflow_hybrid_bot.json` | Workflow n8n completo (importar) |
| `pizzaria/bot_views.py` | Atualizado para processar envelope n8n |
| `pizzaria/views.py` | Novos endpoints `/api/n8n/neighborhoods/` e `/api/n8n/products/` |
| `pizzaria/urls.py` | Rotas para os novos endpoints |

## Arquitetura

```
WAHA → Webhook → Normalizar → Buffer → Router → [LLM?] → Django
                                          │
                                          ├─ SIM: Buscar Bairros + Cardápio → Groq (Llama 3.1) → Parse → Match Bairro → Envelope → Django
                                          │
                                          └─ NÃO: Envelope simples → Django
```

## Variáveis de Ambiente

Configure no n8n (Settings > Environment Variables):

```bash
# API Groq (obrigatório) - GRÁTIS!
GROQ_API_KEY=gsk_xxxxx

# Redis (opcional - para buffer mais robusto)
# REDIS_URL=redis://redis:6379/0
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
    "provider": "groq",
    "model": "llama-3.1-70b-versatile",
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

### Erro "GROQ_API_KEY not found"

Configure a variável de ambiente no n8n:
- Settings > Environment Variables
- Adicione `GROQ_API_KEY`

Para obter a key (grátis):
1. Acesse https://console.groq.com
2. Crie uma conta
3. Vá em API Keys > Create API Key

### Buffer não funciona

O buffer usa `staticData` do n8n (em memória). Para produção com múltiplas instâncias, substitua pelo Redis node.

### LLM retorna JSON inválido

O node "Parse LLM Response" tenta limpar markdown e fazer parse. Se falhar:
- `llm.valid = false`
- `llm.validation_error = "json_parse_error: ..."`
- Django deve usar fallback (menu guiado)

### Match de bairro muito amplo

Ajuste os thresholds no node "Match Bairro Fuzzy":
- Linha com `score >= 90`: aumentar para 95
- Linha com `score >= 75`: aumentar para 80

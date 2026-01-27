# Workflow de Lembretes Automáticos - n8n

## Visão Geral

Este workflow envia lembretes automáticos para pacientes que têm consulta agendada para o dia seguinte.

```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Schedule   │────▶│  HTTP Request│────▶│  Loop Items  │────▶│  WAHA Send   │
│  (18:00)    │     │  (API Django)│     │  (Para cada) │     │  (WhatsApp)  │
└─────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                                                                      │
                                                                      ▼
                                                              ┌──────────────┐
                                                              │ Mark as Sent │
                                                              │ (API Django) │
                                                              └──────────────┘
```

---

## Configuração Passo a Passo

### 1. Criar novo Workflow

1. Acesse o n8n: http://localhost:5678
2. Clique em **+ Create Workflow**
3. Nomeie: "Lembretes de Consulta"

---

### 2. Nó 1: Schedule Trigger

**Tipo:** Schedule Trigger

**Configuração:**
- **Trigger Times:** Custom
- **Cron Expression:** `0 18 * * *` (todos os dias às 18:00)

Ou use a interface:
- **Mode:** Every Day
- **Hour:** 18
- **Minute:** 0

---

### 3. Nó 2: HTTP Request - Buscar Agendamentos

**Tipo:** HTTP Request

**Configuração:**
| Campo | Valor |
|-------|-------|
| Method | GET |
| URL | `http://backend:8000/api/bot/pending-tomorrow` |
| Authentication | None |
| Headers | `X-Bot-Api-Key`: `FAsdff423@$#$2343423442dfgdfgdfgdfg` |

**Response:**
```json
[
  {
    "appointmentId": 4,
    "patientName": "Igor Pereira Dutra",
    "phoneE164": "+556992690072",
    "wahaChatId": "556992690072@c.us",
    "startsAt": "2026-01-26T10:00:00-03:00",
    "message": "Olá, *Igor*! 💙\n\nPassando para lembrar..."
  }
]
```

---

### 4. Nó 3: Loop Over Items

**Tipo:** Split In Batches (ou Loop Over Items)

Este nó itera sobre cada agendamento retornado.

---

### 5. Nó 4: HTTP Request - Enviar WhatsApp (WAHA)

**Tipo:** HTTP Request

**Configuração:**
| Campo | Valor |
|-------|-------|
| Method | POST |
| URL | `http://waha:3000/api/sendText` |
| Body Content Type | JSON |
| Headers | `X-Api-Key`: `6c35dcbf31914c65a90f29e2ca1840d2` |
| Body | Ver abaixo |

**Body (JSON):**
```json
{
  "chatId": "{{ $json.wahaChatId }}",
  "text": "{{ $json.message }}",
  "session": "default"
}
```

**Alternativa com expressão n8n:**
```json
{
  "chatId": "={{$json[\"wahaChatId\"]}}",
  "text": "={{$json[\"message\"]}}",
  "session": "default"
}
```

---

### 6. Nó 5: HTTP Request - Marcar como Enviado

**Tipo:** HTTP Request

**Configuração:**
| Campo | Valor |
|-------|-------|
| Method | POST |
| URL | `http://backend:8000/api/bot/appointments/{{ $json.appointmentId }}/mark-confirmation-sent` |
| Headers | `X-Bot-Api-Key`: `FAsdff423@$#$2343423442dfgdfgdfgdfg` |

Isso evita que o mesmo lembrete seja enviado novamente.

---

## JSON do Workflow Completo

Cole este JSON no n8n (Import from JSON):

```json
{
  "name": "Lembretes de Consulta",
  "nodes": [
    {
      "parameters": {
        "rule": {
          "interval": [
            {
              "field": "cronExpression",
              "expression": "0 18 * * *"
            }
          ]
        }
      },
      "name": "Agendar 18h",
      "type": "n8n-nodes-base.scheduleTrigger",
      "typeVersion": 1.1,
      "position": [250, 300]
    },
    {
      "parameters": {
        "method": "GET",
        "url": "http://backend:8000/api/bot/pending-tomorrow",
        "options": {
          "response": {
            "response": {
              "responseFormat": "json"
            }
          }
        },
        "headerParameters": {
          "parameters": [
            {
              "name": "X-Bot-Api-Key",
              "value": "FAsdff423@$#$2343423442dfgdfgdfgdfg"
            }
          ]
        }
      },
      "name": "Buscar Agendamentos",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.1,
      "position": [450, 300]
    },
    {
      "parameters": {
        "batchSize": 1,
        "options": {}
      },
      "name": "Loop",
      "type": "n8n-nodes-base.splitInBatches",
      "typeVersion": 3,
      "position": [650, 300]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "http://waha:3000/api/sendText",
        "options": {
          "response": {
            "response": {
              "responseFormat": "json"
            }
          }
        },
        "headerParameters": {
          "parameters": [
            {
              "name": "X-Api-Key",
              "value": "6c35dcbf31914c65a90f29e2ca1840d2"
            }
          ]
        },
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={\n  \"chatId\": \"{{ $json.wahaChatId }}\",\n  \"text\": \"{{ $json.message }}\",\n  \"session\": \"default\"\n}"
      },
      "name": "Enviar WhatsApp",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.1,
      "position": [850, 300]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "=http://backend:8000/api/bot/appointments/{{ $json.appointmentId }}/mark-confirmation-sent",
        "options": {},
        "headerParameters": {
          "parameters": [
            {
              "name": "X-Bot-Api-Key",
              "value": "FAsdff423@$#$2343423442dfgdfgdfgdfg"
            }
          ]
        }
      },
      "name": "Marcar Enviado",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.1,
      "position": [1050, 300]
    }
  ],
  "connections": {
    "Agendar 18h": {
      "main": [[{"node": "Buscar Agendamentos", "type": "main", "index": 0}]]
    },
    "Buscar Agendamentos": {
      "main": [[{"node": "Loop", "type": "main", "index": 0}]]
    },
    "Loop": {
      "main": [
        [{"node": "Enviar WhatsApp", "type": "main", "index": 0}],
        []
      ]
    },
    "Enviar WhatsApp": {
      "main": [[{"node": "Marcar Enviado", "type": "main", "index": 0}]]
    },
    "Marcar Enviado": {
      "main": [[{"node": "Loop", "type": "main", "index": 0}]]
    }
  }
}
```

---

## Testando Manualmente

### 1. Testar API de Agendamentos

```bash
curl http://localhost:8000/api/bot/pending-tomorrow \
  -H "X-Bot-Api-Key: FAsdff423@\$#\$2343423442dfgdfgdfgdfg"
```

### 2. Executar Workflow Manualmente

No n8n:
1. Abra o workflow
2. Clique em **Execute Workflow** (ou Test Workflow)
3. Verifique se a mensagem foi enviada no WhatsApp

### 3. Verificar se foi marcado como enviado

```bash
docker-compose exec postgres psql -U chatbot_user -d chatbot \
  -c "SELECT id, confirmation_sent_at FROM appointments WHERE id = 4;"
```

---

## Lembretes no Dia (Opcional)

Para enviar lembrete no próprio dia da consulta (ex: às 7h da manhã):

**Endpoint:** `GET /api/bot/pending-today`

**Cron:** `0 7 * * *` (todos os dias às 7:00)

O JSON do workflow seria similar, apenas mudando:
- URL: `http://backend:8000/api/bot/pending-today`
- Horário do Schedule: 7:00

---

## Troubleshooting

| Problema | Solução |
|----------|---------|
| "Invalid API key" | Verifique o header `X-Bot-Api-Key` |
| Workflow não executa | Verifique se está ativo (toggle no topo) |
| Mensagem não enviada | Verifique se WAHA está conectado |
| Lembrete duplicado | O sistema já marca como enviado, verifique `confirmation_sent_at` |

---

*Documentação criada em Janeiro/2026*

# Atendimento Conversacional — Pizzaria do Negão

Guia do novo modelo de atendimento automático, pensado para clientes que preferem **áudio**, escrevem com **erros** ou não estão familiarizados com menus numéricos.

## Princípio

> O cliente manda do jeito dele (áudio ou texto). O bot repete o pedido. O cliente confirma com **SIM**.

Sem depender de atendente humano.

## Fluxo geral

```
WhatsApp (texto ou áudio)
    → n8n: normaliza → [áudio?] transcreve (Groq Whisper)
    → buffer 3s (junta msgs rápidas)
    → router → LLM (Claude Haiku) quando necessário
    → Django: monta pedido / confirma / finaliza
    → resposta curta no WhatsApp
```

## O que mudou

| Antes | Agora |
|-------|-------|
| Áudio → "liga pra gente" | Áudio → Whisper → mesmo fluxo do texto |
| Menu 1-2-3 no welcome | Mensagem conversacional + exemplos |
| Só máquina de estados | LLM + confirmação de rascunho do pedido |
| Buffer 10s | Buffer **3s** (mais rápido) |
| Cliente perdido | Detector de confusão + mensagem simplificada |

## Áudio (STT)

- **Onde:** node `Processar Audio STT` no workflow n8n
- **Modelo:** `whisper-large-v3-turbo` (Groq)
- **Idioma:** pt (português)
- **Feedback imediato:** "Recebi seu áudio! Só um instante 🎧"
- **Fallback Django:** se WAHA enviar direto ao Django (sem n8n), `pizzaria/audio_service.py` também transcreve

### Variáveis necessárias (n8n)

```bash
ANTHROPIC_API_KEY=sk-ant-xxxxx
GROQ_API_KEY=gsk_xxxxx
WAHA_URL=http://waha:3000
WAHA_API_KEY=sua-api-key
WAHA_SESSION=default
```

### Variáveis Django (fallback STT)

```bash
GROQ_API_KEY=gsk_xxxxx
GROQ_WHISPER_MODEL=whisper-large-v3-turbo
```

## Welcome conversacional

Exemplo enviado ao cliente:

```
Oi! 🍕 Pizzaria do Negão

Manda seu pedido do seu jeito:
• por áudio 🎤
• ou por texto (pode escrever do jeito que quiser)

Exemplo:
"2 calabresa entrega aponia pix"

Também pode falar:
• cardápio — ver sabores
• promo — promoção
• ajuda — como funciona
```

## Confirmação de pedido (rascunho)

Quando o LLM extrai **itens + endereço/retirada + pagamento** com confiança ≥ 75%, o bot envia:

```
Anotei assim: 👇

🍕 2x Calabresa
🏠 Rua X, 123 - Aponiã
💳 PIX
💰 Total: R$ 67.00

Tá certo? Responde SIM ou manda o que mudar
```

Estado: `awaiting_draft_confirmation`

## Cliente confuso

Após **2 tentativas** sem avançar, o bot envia:

```
Vamos simplificar! 😊

Manda um áudio falando:
• quantas pizzas
• sabor
• bairro
• como paga

Eu repito tudo pra você confirmar com SIM
```

Comando manual: `ajuda` ou `como funciona`

## Router n8n — quando usa LLM

| Situação | LLM? |
|----------|------|
| FAQ (horário, local, pagamento, cardápio) | ❌ Resposta fixa |
| Saudação ou "queria pedir pizza" (sem sabor) | ❌ Resposta calorosa |
| Áudio com pedido completo (sabor/endereço) | ✅ Haiku |
| Múltiplas msgs em 3s | ✅ |
| Sabores, endereço, gírias | ✅ |
| "sim", "pix", "1" | ❌ Fluxo direto |
| Transcrição + typos | ✅ (regras 11-13 no prompt) |

### Exemplo: áudio conversacional

*"Oi Jeferson, tudo bem? Queria pedir uma pizza"*

→ Resposta imediata (sem LLM): cumprimento + *"Me fala o sabor (pode ser por áudio)"*

## Cobertura ampliada

### Pedido incompleto — uma pergunta por vez

Cliente: *"2 calabresa"* (sem endereço/pagamento)

```
Anotei até aqui: 👇
🍕 2x Calabresa

Só falta uma coisa:
Qual o endereço? 🏠
```

Depois pergunta pagamento — nunca tudo de uma vez.

### Repetir último pedido

Cliente: *"repetir"* / *"o de sempre"* / *"mesmo pedido"*

→ Bot monta último pedido e pergunta: *"Quer repetir? SIM ou Mudar"*

### Botões WhatsApp

Em pagamento, entrega/retirada e confirmação: botões *PIX | Dinheiro | Cartão* e *SIM | Mudar* (fallback para texto se WAHA não suportar).

## Arquivos principais

| Arquivo | Função |
|---------|--------|
| `n8n_workflow_hybrid_bot.json` | Workflow com STT + LLM |
| `pizzaria/bot_views.py` | Lógica do bot, confirmação, áudio fallback |
| `pizzaria/audio_service.py` | Transcrição Groq Whisper (Django) |
| `pizzaria/conversational_helpers.py` | Welcome, ajuda, rascunho, confusão |
| `scripts/patch_n8n_workflow.py` | Script que aplica patches no workflow |

## Deploy / atualização

### Local (docker-compose)

1. Configure `ANTHROPIC_API_KEY` (LLM) e `GROQ_API_KEY` (áudio) no `.env`
2. `docker-compose up --build -d`
3. Importe ou reimporte `n8n_workflow_hybrid_bot.json` no n8n
4. Ative o workflow híbrido (desative o antigo `n8n_workflow_pizzaria.json`)

### Railway

Adicione as mesmas variáveis no serviço **n8n** e **Django**:

- `ANTHROPIC_API_KEY`, `ANTHROPIC_LLM_MODEL`
- `GROQ_API_KEY`
- `WAHA_URL`, `WAHA_API_KEY`, `WAHA_SESSION`

## Testes recomendados

### 1. Áudio simples
Envie áudio: *"quero duas calabresa"*
- Esperado: ack 🎧 → transcrição → anotação do pedido

### 2. Pedido completo por áudio
*"duas calabresa entrega henrique soares 6225 aponia pix"*
- Esperado: resumo + "Tá certo? Responde SIM"

### 3. Texto com erro
*"2 klabresa entrega aponia"*
- Esperado: LLM interpreta calabresa

### 4. Cliente perdido
Envie mensagens sem sentido 2x
- Esperado: "Vamos simplificar..."

### 5. Ajuda
Digite `ajuda`
- Esperado: tutorial em 4 passos

## Troubleshooting

### Áudio não transcreve
- Verifique `GROQ_API_KEY` no n8n
- Verifique `WAHA_API_KEY` e se o áudio chega no webhook
- Logs: `docker-compose logs -f n8n`

### "Não consegui entender o áudio"
- Áudio muito curto ou ruído — peça para repetir
- Teste download manual via WAHA API

### LLM não monta pedido completo
- Cliente pode não ter falado pagamento/endereço — bot pergunta só o que falta
- Confiança < 75% → fluxo passo a passo normal

### Resposta lenta
- Whisper ~1-2s + LLM ~1-2s + buffer 3s = ~5s total (normal)
- Ack imediato evita cliente achar que travou

---

*Documentação atualizada: Junho/2026*

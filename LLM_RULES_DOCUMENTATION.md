# Documentação das Regras do LLM - Pizzaria Bot

## Visão Geral

O sistema utiliza o modelo **Llama 3.3 70B** via **Groq API** para interpretar mensagens de clientes em linguagem natural e extrair informações estruturadas (intenção, entidades, pedidos).

## Arquitetura

```
Cliente (WhatsApp) → WAHA → n8n → Groq LLM → Django
                              ↓
                    [Router decide se usa LLM]
                              ↓
                    [Se sim: busca cardápio + bairros]
                              ↓
                    [Envia para Groq com contexto]
                              ↓
                    [Parse da resposta JSON]
                              ↓
                    [Match fuzzy de bairro]
                              ↓
                    [Envelope para Django processar]
```

---

## Informações da Pizzaria (Contexto Fixo)

O LLM recebe estas informações fixas sobre a pizzaria:

| Informação | Valor |
|------------|-------|
| Tamanho único | G (Grande - 8 pedaços) |
| Tamanhos que NÃO existem | P, M, média, pequena, família, broto |
| Promoção | 2 pizzas por R$ 55,00 |

---

## Regras de Extração

### Regra 1: Não Inventar Dados
- Se não conseguir identificar um dado, deixar `null` ou string vazia
- Nunca assumir informações não fornecidas pelo cliente

### Regra 2: Endereços
- Extrair partes do endereço (rua, número, bairro, complemento, referência)
- **NÃO** decidir qual é o bairro canônico (isso é feito pelo match fuzzy depois)

### Regra 3: Pedidos de Pizza
- Extrair sabores mencionados
- **NÃO** assumir meio-a-meio sem indicação clara do cliente
- Se detectar 2 sabores juntos sem clareza, marcar `ambiguous: true`

### Regra 4: Modificadores (Observações)
| Padrão do Cliente | Tipo | Exemplo |
|-------------------|------|---------|
| "sem X", "tirar X", "tira X" | `remove` | "sem cebola" → `{type: "remove", ingredient: "cebola"}` |
| "com extra X", "adicionar X" | `add` | "com extra queijo" → `{type: "add", ingredient: "queijo"}` |

### Regra 5: Indicadores de Item Adicional
Palavras que indicam que o cliente quer adicionar mais itens:
- "tbm", "tb", "também"
- "e a outra", "mais uma"
- "e também"

### Regra 6: Ambiguidade de Sabores
Quando detectar 2 sabores juntos (ex: "calabresa e queijo"):
```json
{
  "order": {
    "ambiguous": true,
    "ambiguity_reason": "2 sabores mencionados - pode ser meio a meio ou 2 pizzas"
  }
}
```

### Regra 7: Números Sozinhos
- Números sozinhos (1, 2, 3...) geralmente são **seleção de menu**, não quantidade
- Exemplo: "1" = primeira opção do menu, não "1 pizza"

### Regra 8: Tamanhos Inválidos
Se o cliente mencionar tamanho diferente de G:
```json
{
  "order": {
    "items": [{"name": "calabresa", "size_requested": "media"}],
    "invalid_size": true
  }
}
```

**Tamanhos que ativam `invalid_size`:**
- média, media, m
- pequena, p, broto
- família, familia, gg, gigante

### Regra 9: Identificação de Promoção
Se o cliente mencionar promoção, marcar `is_promo: true`:

**Palavras-chave de promoção:**
- "promoção", "promocao", "promo"
- "2 por 55", "duas por 55"
- "combo", "oferta"

### Regra 10: Múltiplas Promoções (Pares)
Quando o cliente pedir várias pizzas da promoção, agrupar em pares:

**Entrada:** "quero 4 pizzas da promoção: calabresa, bacon, portuguesa e 4 queijos"

**Saída:**
```json
{
  "order": {
    "is_promo": true,
    "promo_pairs": [
      ["calabresa", "bacon"],
      ["portuguesa", "4 queijos"]
    ]
  }
}
```

---

## Schema de Saída (JSON)

```json
{
  "intent": "provide_address|choose_delivery_type|choose_payment|provide_change|add_item|order_build|confirm|deny|greeting|menu_request|other",
  "entities": {
    "delivery_type": "delivery|pickup|unknown",
    "payment_method": "pix|cash|credit|debit|unknown",
    "change_for": null,
    "address": {
      "address_line": "",
      "neighborhood_text": "",
      "number": "",
      "complement": "",
      "reference": ""
    },
    "order": {
      "items": [
        {
          "name": "",
          "quantity": 1,
          "size_requested": null,
          "modifiers": [
            {"type": "remove|add", "ingredient": ""}
          ],
          "notes": ""
        }
      ],
      "is_half_half": false,
      "is_promo": false,
      "promo_pairs": [],
      "invalid_size": false,
      "ambiguous": false,
      "ambiguity_reason": ""
    }
  },
  "missing_fields": [],
  "suggested_questions": [],
  "confidence": 0.0
}
```

---

## Intents (Intenções)

| Intent | Descrição | Exemplo de Mensagem |
|--------|-----------|---------------------|
| `add_item` | Adicionar pizza ao pedido | "quero uma calabresa" |
| `order_build` | Construir pedido completo | "2 calabresa e 1 portuguesa" |
| `provide_address` | Fornecer endereço | "rua das flores 123 centro" |
| `choose_delivery_type` | Escolher entrega/retirada | "entrega" |
| `choose_payment` | Escolher pagamento | "pix" |
| `provide_change` | Informar troco | "troco pra 100" |
| `confirm` | Confirmar algo | "sim", "ok", "isso" |
| `deny` | Negar algo | "não", "cancela" |
| `greeting` | Saudação | "oi", "boa noite" |
| `menu_request` | Pedir cardápio | "quero ver o cardápio" |
| `other` | Não identificado | - |

---

## Exemplos de Interpretação

### Exemplo 1: Tamanho Inválido
**Entrada:** "quero uma pizza média de calabresa"

**Saída:**
```json
{
  "intent": "add_item",
  "entities": {
    "order": {
      "items": [{"name": "calabresa", "quantity": 1, "size_requested": "media"}],
      "invalid_size": true
    }
  },
  "confidence": 0.9
}
```

### Exemplo 2: Múltiplas Promoções
**Entrada:** "quero 4 pizzas da promoção: calabresa, bacon, portuguesa e 4 queijos"

**Saída:**
```json
{
  "intent": "order_build",
  "entities": {
    "order": {
      "items": [
        {"name": "calabresa", "quantity": 1},
        {"name": "bacon", "quantity": 1},
        {"name": "portuguesa", "quantity": 1},
        {"name": "4 queijos", "quantity": 1}
      ],
      "is_promo": true,
      "promo_pairs": [
        ["calabresa", "bacon"],
        ["portuguesa", "4 queijos"]
      ]
    }
  },
  "confidence": 0.95
}
```

### Exemplo 3: Pizza com Observação
**Entrada:** "uma calabresa sem cebola e com extra queijo"

**Saída:**
```json
{
  "intent": "add_item",
  "entities": {
    "order": {
      "items": [{
        "name": "calabresa",
        "quantity": 1,
        "modifiers": [
          {"type": "remove", "ingredient": "cebola"},
          {"type": "add", "ingredient": "queijo"}
        ]
      }]
    }
  },
  "confidence": 0.95
}
```

### Exemplo 4: Endereço Completo
**Entrada:** "rua henrique soares 6225 apt 102 aponia perto do mercado"

**Saída:**
```json
{
  "intent": "provide_address",
  "entities": {
    "address": {
      "address_line": "rua henrique soares",
      "number": "6225",
      "complement": "apt 102",
      "neighborhood_text": "aponia",
      "reference": "perto do mercado"
    }
  },
  "confidence": 0.9
}
```

### Exemplo 5: Dois Sabores (Ambíguo)
**Entrada:** "calabresa e 4 queijos"

**Saída:**
```json
{
  "intent": "add_item",
  "entities": {
    "order": {
      "items": [
        {"name": "calabresa", "quantity": 1},
        {"name": "4 queijos", "quantity": 1}
      ],
      "ambiguous": true,
      "ambiguity_reason": "2 sabores mencionados - pode ser meio a meio ou 2 pizzas separadas"
    }
  },
  "confidence": 0.7
}
```

### Exemplo 6: Meio a Meio Explícito
**Entrada:** "metade calabresa metade 4 queijos"

**Saída:**
```json
{
  "intent": "add_item",
  "entities": {
    "order": {
      "items": [
        {"name": "calabresa", "quantity": 1},
        {"name": "4 queijos", "quantity": 1}
      ],
      "is_half_half": true,
      "ambiguous": false
    }
  },
  "confidence": 0.95
}
```

---

## Padrões SAFE (Não Usam LLM)

O router no n8n identifica padrões "seguros" que não precisam de LLM:

| Padrão | Exemplos |
|--------|----------|
| Números simples | 1, 2, 15 |
| Confirmações | sim, não, ok, beleza |
| Pagamento | pix, dinheiro, cartão |
| Entrega | entrega, retirada |
| Valores | R$ 100, 50 |
| Comandos | voltar, cancelar, menu |
| Saudações simples | oi, olá |

---

## Padrões que USAM LLM

| Condição | Exemplo |
|----------|---------|
| Múltiplas mensagens (buffer > 1) | Mensagens enviadas rapidamente |
| Texto com sabores | "calabresa", "4 queijos" |
| Endereços | "rua", "avenida", número |
| Modificadores | "sem", "tirar", "extra" |
| Gírias | "tbm", "outra", "mais uma" |
| Meio a meio | "meio", "metade" |
| Mais de 3 palavras | Frases complexas |

---

## Configuração do Modelo

| Parâmetro | Valor |
|-----------|-------|
| Modelo | `llama-3.3-70b-versatile` |
| Provider | Groq |
| Temperature | 0.1 (baixa para respostas consistentes) |
| Response Format | JSON Object |
| Timeout | 15 segundos |

---

## Fluxo de Processamento no Django

1. **Recebe envelope do n8n** com resultado do LLM
2. **Verifica `invalid_size`** → Informa que só tem G
3. **Verifica `is_promo` + `promo_pairs`** → Processa múltiplas promoções
4. **Verifica `ambiguous`** → Pergunta se é meio a meio ou separadas
5. **Processa items** → Match fuzzy com produtos cadastrados
6. **Processa modifiers** → Adiciona observações
7. **Atualiza estado** da conversa
8. **Envia resposta** ao cliente

---

## Match Fuzzy de Bairro

| Score | Ação |
|-------|------|
| >= 90 | Aceita automaticamente |
| 75-89 | Pede confirmação ao cliente |
| < 75 | Pede para digitar novamente |

---

## Manutenção

### Adicionar Novo Tamanho
Se a pizzaria passar a ter outros tamanhos:
1. Remover a informação "só existe G" do prompt
2. Remover a regra de `invalid_size`
3. Adicionar campo `size` no schema

### Alterar Preço da Promoção
1. Buscar "R$55" no prompt e alterar
2. Alterar `promo_price` no Django (`bot_views.py`)

### Adicionar Novos Modificadores
1. Adicionar padrões na Regra 4 do prompt
2. Atualizar função `extract_observation()` no Django

---

## Troubleshooting

### LLM retorna JSON inválido
- O node "Parse LLM Response" tenta limpar markdown
- Se falhar: `llm.valid = false`, Django usa fluxo guiado

### Tamanho não detectado
- Verificar se o tamanho está na lista de palavras-chave
- Adicionar variações no prompt

### Promoção não identificada
- Verificar se usou palavras-chave de promoção
- Cliente pode não ter mencionado "promoção"

---

*Documentação atualizada em: Fevereiro/2026*

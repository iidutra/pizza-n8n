# Setup - Pizzaria do Negao

## Arquitetura

```
WhatsApp Usuario <-> WAHA <-> n8n <-> Django Backend <-> PostgreSQL
                                           |
                                         Redis (estado conversacional)
```

## Servicos

| Servico | Porta | Descricao |
|---------|-------|-----------|
| Django  | 8000  | Backend + Dashboard |
| n8n     | 5678  | Automacao/Workflow |
| WAHA    | 3000  | API WhatsApp |
| PostgreSQL | 5432 | Banco de dados |
| Redis   | 6379  | Cache/Estado |

## Inicializacao Rapida

### 1. Subir os containers

```bash
docker-compose up --build -d
```

### 2. Acessar o n8n e importar o workflow

1. Acesse: http://localhost:5678
2. Login: `admin` / `admin123`
3. Clique em "Import workflow"
4. Selecione o arquivo **`n8n_workflow_hybrid_bot.json`** (recomendado — áudio + LLM)
5. Configure `ANTHROPIC_API_KEY` (LLM) e `GROQ_API_KEY` (áudio) no `.env` ou nas variáveis do container n8n
6. Ative o workflow (toggle no canto superior direito)
7. **Desative** o workflow antigo `n8n_workflow_pizzaria.json` se existir

> Documentação completa do atendimento conversacional: [ATENDIMENTO_CONVERSACIONAL.md](ATENDIMENTO_CONVERSACIONAL.md)

### 3. Configurar o WAHA (WhatsApp)

1. Acesse: http://localhost:3000/api/docs
2. Crie uma sessao:
   ```bash
   curl -X POST "http://localhost:3000/api/sessions/start" \
     -H "Content-Type: application/json" \
     -d '{"name": "default"}'
   ```
3. Escaneie o QR Code que aparece no terminal do WAHA
4. Aguarde a conexao

### 4. Acessar o Dashboard

1. Acesse: http://localhost:8000
2. Login: `admin` / `admin123`

## Credenciais Padrao

| Sistema | Usuario | Senha |
|---------|---------|-------|
| Django Dashboard | admin | admin123 |
| Django Admin | admin | admin123 |
| n8n | admin | admin123 |

## Fluxo do Workflow n8n

```
WAHA Webhook
     |
     v
[E evento de mensagem?] --Nao--> Ignorar
     |
    Sim
     v
[E mensagem minha?] --Sim--> Ignorar
     |
    Nao
     v
[E imagem?] --Sim--> Buscar URL da midia --> Enviar ao Django
     |
    Nao
     v
Enviar ao Django --> Responder OK
```

## Endpoints da API

| Metodo | Endpoint | Descricao |
|--------|----------|-----------|
| POST | /api/bot/message/ | Webhook do bot (recebe do n8n) |
| GET | /api/orders/ | Lista pedidos |
| PATCH | /api/orders/{id}/update_status/ | Atualiza status |
| POST | /api/orders/{id}/confirm_payment/ | Confirma pagamento |
| GET | /api/products/ | Lista produtos |
| GET | /api/delivery-fees/ | Lista taxas |
| GET/PATCH | /api/settings/ | Configuracoes |
| GET | /api/reports/summary/ | Relatorio resumo |
| GET | /api/reports/top-products/ | Produtos mais vendidos |
| GET | /api/reports/hourly/ | Pedidos por hora |
| GET | /api/reports/neighborhoods/ | Pedidos por bairro |

## Testando o Bot

1. Envie uma mensagem para o numero conectado no WAHA
2. Exemplos de mensagens:
   - "Boa noite, quero uma pizza"
   - "calabresa"
   - **Áudio:** "duas calabresa entrega aponia pix"
   - [Enviar imagem do comprovante]
3. Digite `ajuda` para ver como funciona o atendimento

## Logs

```bash
# Ver logs de todos os servicos
docker-compose logs -f

# Ver logs do Django
docker-compose logs -f web

# Ver logs do WAHA
docker-compose logs -f waha

# Ver logs do n8n
docker-compose logs -f n8n
```

## Troubleshooting

### WAHA nao conecta
- Verifique se o QR code foi escaneado
- Reinicie o container: `docker-compose restart waha`

### Mensagens nao chegam no Django
- Verifique se o workflow do n8n esta ativo
- Verifique os logs do n8n: `docker-compose logs -f n8n`

### Erro de banco de dados
- Verifique se o PostgreSQL esta rodando: `docker-compose ps`
- Recriar banco: `docker-compose down -v && docker-compose up --build`

## Producao

Para deploy em producao:

1. Altere as senhas no `.env`
2. Configure `DEBUG=False`
3. Use um dominio com HTTPS
4. Configure backup do PostgreSQL
5. Use um servidor SMTP para emails (opcional)

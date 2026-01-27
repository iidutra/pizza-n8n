# Deploy em PaaS (Platform as a Service)

## Opções de PaaS Recomendadas

| PaaS | PostgreSQL | Redis | Docker | Custo Inicial |
|------|------------|-------|--------|---------------|
| **Railway** | ✅ Incluído | ✅ Incluído | ✅ | ~$5/mês |
| **Render** | ✅ Incluído | ✅ Incluído | ✅ | ~$7/mês |
| **Fly.io** | ✅ Incluído | ✅ Incluído | ✅ | ~$5/mês |
| **DigitalOcean App** | ✅ Addon | ✅ Addon | ✅ | ~$12/mês |

---

## Railway (Recomendado)

Railway é a opção mais simples para deploy de múltiplos serviços Docker.

### 1. Preparar o Projeto

```bash
# Inicialize o git
cd atendimento-n8n
git init
git add .
git commit -m "Initial commit"

# Crie repositório no GitHub
gh repo create atendimento-n8n --private --source=. --push
```

### 2. Criar Projeto no Railway

1. Acesse https://railway.app
2. Clique em **New Project**
3. Selecione **Deploy from GitHub repo**
4. Autorize e selecione o repositório

### 3. Adicionar Serviços

No Railway, adicione cada serviço:

#### PostgreSQL
1. Clique em **+ New**
2. Selecione **Database → PostgreSQL**
3. Anote a `DATABASE_URL` gerada

#### Redis
1. Clique em **+ New**
2. Selecione **Database → Redis**
3. Anote a `REDIS_URL` gerada

#### Backend Django
1. Clique em **+ New → GitHub Repo**
2. Configure:
   - **Root Directory:** `/`
   - **Dockerfile:** `Dockerfile.prod`
3. Adicione variáveis de ambiente (ver abaixo)

#### n8n
1. Clique em **+ New → Docker Image**
2. Image: `n8nio/n8n:latest`
3. Configure variáveis de ambiente

#### WAHA
1. Clique em **+ New → Docker Image**
2. Image: `devlikeapro/waha:latest`
3. Configure variáveis de ambiente

### 4. Variáveis de Ambiente - Backend

```env
DJANGO_SECRET_KEY=railway-generated-or-custom
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=seu-app.railway.app
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
BOT_API_KEY=sua-chave-secreta
TZ=America/Sao_Paulo
```

### 5. Variáveis de Ambiente - n8n

```env
N8N_HOST=seu-app-n8n.railway.app
N8N_PORT=5678
N8N_PROTOCOL=https
WEBHOOK_URL=https://seu-app-n8n.railway.app
N8N_BASIC_AUTH_ACTIVE=true
N8N_BASIC_AUTH_USER=admin
N8N_BASIC_AUTH_PASSWORD=sua-senha-forte
N8N_ENCRYPTION_KEY=chave-32-caracteres
DB_TYPE=postgresdb
DB_POSTGRESDB_HOST=${{Postgres.PGHOST}}
DB_POSTGRESDB_PORT=${{Postgres.PGPORT}}
DB_POSTGRESDB_DATABASE=${{Postgres.PGDATABASE}}
DB_POSTGRESDB_USER=${{Postgres.PGUSER}}
DB_POSTGRESDB_PASSWORD=${{Postgres.PGPASSWORD}}
```

### 6. Variáveis de Ambiente - WAHA

```env
WAHA_API_KEY=sua-chave-waha
WAHA_DASHBOARD_ENABLED=true
WAHA_DASHBOARD_USERNAME=admin
WAHA_DASHBOARD_PASSWORD=sua-senha-forte
WHATSAPP_HOOK_URL=https://seu-app-n8n.railway.app/webhook/waha-inbound
WHATSAPP_HOOK_EVENTS=message,session.status
WHATSAPP_DEFAULT_ENGINE=GOWS
REDIS_URL=${{Redis.REDIS_URL}}
```

### 7. Configurar Domínios

1. Em cada serviço, vá em **Settings → Domains**
2. Adicione domínio customizado ou use o `.railway.app`

---

## Render

### 1. Criar Web Services

#### Backend
1. New → Web Service
2. Connect GitHub repo
3. Settings:
   - **Environment:** Docker
   - **Dockerfile Path:** `Dockerfile.prod`

#### n8n
1. New → Web Service
2. Settings:
   - **Environment:** Docker
   - **Docker Command:** (deixe vazio)
   - **Image URL:** `n8nio/n8n:latest`

### 2. Criar Databases

1. New → PostgreSQL
2. New → Redis

### 3. Configurar Environment Groups

Crie um Environment Group com as variáveis compartilhadas e vincule aos serviços.

---

## Fly.io

### 1. Instalar CLI

```bash
# macOS
brew install flyctl

# Windows
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

### 2. Login e Deploy

```bash
fly auth login

# Deploy backend
fly launch --dockerfile Dockerfile.prod --name meu-agendamento-backend

# Criar PostgreSQL
fly postgres create --name meu-agendamento-db
fly postgres attach meu-agendamento-db --app meu-agendamento-backend

# Criar Redis
fly redis create --name meu-agendamento-redis
```

### 3. Configurar Secrets

```bash
fly secrets set \
  DJANGO_SECRET_KEY="sua-chave" \
  DJANGO_DEBUG="False" \
  BOT_API_KEY="sua-chave-bot" \
  --app meu-agendamento-backend
```

---

## Arquitetura Multi-Serviço

```
┌─────────────────────────────────────────────────────────────┐
│                         RAILWAY                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │   Backend   │  │     n8n     │  │    WAHA     │          │
│  │   Django    │  │  Workflows  │  │  WhatsApp   │          │
│  │  :8000      │  │   :5678     │  │   :3000     │          │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘          │
│         │                │                │                  │
│         └────────────────┼────────────────┘                  │
│                          │                                   │
│              ┌───────────┴───────────┐                      │
│              │                       │                      │
│         ┌────┴────┐            ┌────┴────┐                  │
│         │PostgreSQL│            │  Redis  │                  │
│         │  :5432   │            │  :6379  │                  │
│         └─────────┘            └─────────┘                  │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Configuração de Webhooks

Após o deploy, configure os webhooks:

### WAHA → n8n
```
WHATSAPP_HOOK_URL=https://seu-n8n.railway.app/webhook/waha-inbound
```

### n8n → Backend
No workflow, use a URL interna do Railway:
```
http://backend.railway.internal:8000/api/bot/inbound
```

Ou a URL pública:
```
https://seu-backend.railway.app/api/bot/inbound
```

---

## Checklist de Deploy

- [ ] Repositório no GitHub (privado)
- [ ] Variáveis de ambiente configuradas
- [ ] PostgreSQL criado e conectado
- [ ] Redis criado e conectado
- [ ] Backend deployado e rodando
- [ ] n8n deployado e rodando
- [ ] WAHA deployado e rodando
- [ ] Workflows importados no n8n
- [ ] Credenciais configuradas no n8n
- [ ] Webhook WAHA → n8n funcionando
- [ ] WhatsApp conectado (QR Code)
- [ ] Domínio customizado (opcional)
- [ ] SSL/HTTPS ativo
- [ ] Teste de agendamento completo

---

## Custos Estimados (Railway)

| Serviço | Recurso | Custo/mês |
|---------|---------|-----------|
| Backend | 512MB RAM | ~$2.50 |
| n8n | 1GB RAM | ~$5.00 |
| WAHA | 1GB RAM | ~$5.00 |
| PostgreSQL | 1GB | ~$2.50 |
| Redis | 256MB | ~$1.00 |
| **Total** | | **~$16/mês** |

*Valores aproximados, podem variar com uso.*

---

## Troubleshooting

### Erro: "Connection refused" entre serviços
- Use URLs internas: `http://servico.railway.internal:porta`

### WAHA não conecta ao WhatsApp
- Verifique se o volume está persistindo a sessão
- Configure `WAHA_RESTART_ALL_SESSIONS=true`

### Webhooks não funcionam
- Verifique se as URLs estão corretas
- Teste com curl: `curl -X POST https://seu-n8n.railway.app/webhook/waha-inbound`

---

*Documentação criada em Janeiro/2026*

# Deploy no Railway - Pizzaria do Negao

Este guia explica como fazer o deploy completo do sistema no Railway.

## Arquitetura

O sistema possui 4 servicos:

| Servico | Descricao | Porta |
|---------|-----------|-------|
| **Backend (Django)** | API e painel administrativo | 8000 |
| **N8N** | Automacao de fluxos | 5678 |
| **WAHA** | API do WhatsApp | 3000 |
| **PostgreSQL** | Banco de dados | 5432 |
| **Redis** | Cache e filas | 6379 |

---

## Passo 1: Criar conta no Railway

1. Acesse [railway.app](https://railway.app)
2. Crie uma conta usando GitHub
3. Adicione um metodo de pagamento (o plano gratuito tem limitacoes)

---

## Passo 2: Criar o Projeto Principal

### 2.1 Deploy do Backend Django

1. No Railway, clique em **"New Project"**
2. Selecione **"Deploy from GitHub repo"**
3. Escolha o repositorio `pizza-n8n`
4. O Railway vai detectar o `railway.toml` automaticamente

### 2.2 Adicionar PostgreSQL

1. No projeto, clique em **"+ New"** → **"Database"** → **"Add PostgreSQL"**
2. Aguarde a criacao do banco
3. O Railway cria automaticamente a variavel `DATABASE_URL`

### 2.3 Adicionar Redis

1. Clique em **"+ New"** → **"Database"** → **"Add Redis"**
2. Aguarde a criacao
3. O Railway cria automaticamente a variavel `REDIS_URL`

### 2.4 Configurar Variaveis do Backend

No servico do backend, va em **"Variables"** e adicione:

```bash
# Django
SECRET_KEY=gere-uma-chave-secreta-com-pelo-menos-50-caracteres
DEBUG=False
ALLOWED_HOSTS=.railway.app

# CORS e CSRF (substitua pelo seu dominio)
CORS_ALLOWED_ORIGINS=https://seu-backend.up.railway.app
CSRF_TRUSTED_ORIGINS=https://seu-backend.up.railway.app

# WAHA (sera configurado depois)
WAHA_URL=https://seu-waha.up.railway.app
WAHA_SESSION=default
WAHA_API_KEY=sua-api-key-segura
```

**Vincular variaveis do banco:**
- Clique em **"Add Reference"**
- Vincule `DATABASE_URL` do PostgreSQL
- Vincule `REDIS_URL` do Redis

---

## Passo 3: Deploy do N8N

### 3.1 Criar novo servico para N8N

**Opcao A - Via GitHub (recomendado):**
1. Crie um novo repositorio no GitHub chamado `pizzaria-n8n`
2. Copie os arquivos da pasta `railway-services/n8n/` para esse repositorio
3. No Railway, clique em **"+ New"** → **"GitHub Repo"**
4. Selecione o repositorio `pizzaria-n8n`

**Opcao B - Via Docker Image:**
1. No projeto Railway, clique em **"+ New"** → **"Docker Image"**
2. Use a imagem: `n8nio/n8n:latest`

### 3.2 Adicionar PostgreSQL para N8N

1. Clique em **"+ New"** → **"Database"** → **"Add PostgreSQL"**
2. Este banco sera exclusivo do N8N

### 3.3 Configurar Variaveis do N8N

```bash
# Timezone
TZ=America/Sao_Paulo

# URLs (substitua pelo seu dominio)
N8N_HOST=0.0.0.0
N8N_PROTOCOL=https
WEBHOOK_URL=https://seu-n8n.up.railway.app
N8N_EDITOR_BASE_URL=https://seu-n8n.up.railway.app

# Autenticacao (USE SENHAS FORTES!)
N8N_BASIC_AUTH_ACTIVE=true
N8N_BASIC_AUTH_USER=admin
N8N_BASIC_AUTH_PASSWORD=SuaSenhaForte123!

# Criptografia (gere uma chave unica de 32+ caracteres)
N8N_ENCRYPTION_KEY=chave-criptografia-unica-32chars

# Banco PostgreSQL (use referencias do Railway)
DB_TYPE=postgresdb
DB_POSTGRESDB_HOST=${PGHOST}
DB_POSTGRESDB_PORT=${PGPORT}
DB_POSTGRESDB_DATABASE=${PGDATABASE}
DB_POSTGRESDB_USER=${PGUSER}
DB_POSTGRESDB_PASSWORD=${PGPASSWORD}

# Seguranca
N8N_SECURE_COOKIE=true
```

**Importante:** Vincule as variaveis do PostgreSQL usando **"Add Reference"**.

---

## Passo 4: Deploy do WAHA

### 4.1 Criar novo servico para WAHA

**Opcao A - Via GitHub (recomendado):**
1. Crie um repositorio `pizzaria-waha`
2. Copie os arquivos da pasta `railway-services/waha/`
3. Deploy via GitHub no Railway

**Opcao B - Via Docker Image:**
1. No Railway, clique em **"+ New"** → **"Docker Image"**
2. Use a imagem: `devlikeapro/waha:latest`

### 4.2 Configurar Variaveis do WAHA

```bash
# API Key (USE UMA CHAVE FORTE!)
WAHA_API_KEY=sua-api-key-muito-segura-123

# Dashboard
WAHA_DASHBOARD_ENABLED=true
WAHA_DASHBOARD_USERNAME=admin
WAHA_DASHBOARD_PASSWORD=SuaSenhaForte123!

# Swagger
WHATSAPP_SWAGGER_ENABLED=true
WHATSAPP_SWAGGER_USERNAME=admin
WHATSAPP_SWAGGER_PASSWORD=SuaSenhaForte123!

# Engine
WHATSAPP_DEFAULT_ENGINE=GOWS

# QR Code
WAHA_PRINT_QR=true

# Webhook para N8N (substitua pelo dominio do seu N8N)
WHATSAPP_HOOK_URL=https://seu-n8n.up.railway.app/webhook/waha-inbound
WHATSAPP_HOOK_EVENTS=message,session.status
WHATSAPP_HOOK_RETRIES_POLICY=linear
WHATSAPP_HOOK_RETRIES_DELAY_SECONDS=2
WHATSAPP_HOOK_RETRIES_ATTEMPTS=4

# Timezone
TZ=America/Sao_Paulo
```

### 4.3 Volume Persistente (Importante!)

O WAHA precisa de armazenamento persistente para manter a sessao do WhatsApp.
No Railway, va em **"Settings"** do servico WAHA e adicione um volume:

- **Mount Path:** `/app/.sessions`

---

## Passo 5: Conectar os Servicos

Apos todos os servicos estarem rodando, atualize as URLs:

### No Backend Django:
```bash
WAHA_URL=https://[seu-waha].up.railway.app
```

### No WAHA:
```bash
WHATSAPP_HOOK_URL=https://[seu-n8n].up.railway.app/webhook/waha-inbound
```

### No N8N:
Configure o workflow para chamar:
- Backend: `https://[seu-backend].up.railway.app/api/bot/message`

---

## Passo 6: Importar Workflow no N8N

1. Acesse seu N8N: `https://seu-n8n.up.railway.app`
2. Faca login com usuario/senha configurados
3. Va em **"Workflows"** → **"Import from File"**
4. Importe o arquivo `n8n_workflow_pizzaria.json`
5. Atualize as URLs no workflow para os novos dominios
6. Ative o workflow

---

## Passo 7: Conectar WhatsApp

1. Acesse o dashboard do WAHA: `https://seu-waha.up.railway.app/dashboard`
2. Faca login
3. Crie uma nova sessao chamada `default`
4. Escaneie o QR Code com seu WhatsApp

---

## Resumo das URLs

Apos o deploy, voce tera:

| Servico | URL |
|---------|-----|
| Backend/Painel | `https://seu-backend.up.railway.app` |
| N8N | `https://seu-n8n.up.railway.app` |
| WAHA Dashboard | `https://seu-waha.up.railway.app/dashboard` |
| WAHA API | `https://seu-waha.up.railway.app/api` |

---

## Custos Estimados (Railway)

| Servico | RAM | Custo Estimado/mes |
|---------|-----|-------------------|
| Backend Django | 512MB | ~$5 |
| N8N | 512MB | ~$5 |
| WAHA | 512MB-1GB | ~$5-10 |
| PostgreSQL x2 | 512MB cada | ~$5 cada |
| Redis | 256MB | ~$2.50 |
| **Total** | | **~$27-32/mes** |

*Valores aproximados, podem variar conforme uso.*

---

## Troubleshooting

### WAHA nao mantem sessao
- Verifique se o volume persistente esta configurado
- Path deve ser `/app/.sessions`

### N8N nao recebe webhooks
- Verifique se `WEBHOOK_URL` esta correto
- Confirme que o workflow esta ativo

### Erro de CORS no Backend
- Adicione o dominio em `CORS_ALLOWED_ORIGINS`
- Adicione em `CSRF_TRUSTED_ORIGINS`

### Banco de dados nao conecta
- Verifique se as variaveis estao vinculadas corretamente
- Use **"Add Reference"** para vincular do PostgreSQL

---

## Gerando Chaves Seguras

Use este comando para gerar chaves:

```bash
# SECRET_KEY do Django (50+ caracteres)
python -c "import secrets; print(secrets.token_urlsafe(50))"

# N8N_ENCRYPTION_KEY (32 caracteres)
python -c "import secrets; print(secrets.token_urlsafe(24))"

# API Keys
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## Suporte

Em caso de problemas:
- Railway Docs: https://docs.railway.app
- N8N Docs: https://docs.n8n.io
- WAHA Docs: https://waha.devlike.pro

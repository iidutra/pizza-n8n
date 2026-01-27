# Deploy em Produção

Guia completo para publicar o sistema de agendamentos em produção.

---

## 1. Pré-requisitos

- Servidor Linux (Ubuntu 22.04+ recomendado)
- Docker e Docker Compose instalados
- Domínio apontando para o IP do servidor
- Portas 80 e 443 liberadas no firewall

---

## 2. Estrutura de Arquivos

```
/opt/chatbot-agenda/
├── docker-compose.prod.yml
├── .env.prod
├── nginx/
│   └── nginx.conf
├── init/
│   └── 01_schema.sql
├── agenda/
├── backend/
└── backups/
```

---

## 3. Arquivo de Variáveis de Ambiente

Crie o arquivo `.env.prod`:

```env
# Django
DJANGO_SECRET_KEY=sua-chave-secreta-muito-longa-e-aleatoria-aqui-min-50-chars
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=seu-dominio.com.br,www.seu-dominio.com.br

# Banco de Dados
POSTGRES_DB=chatbot_prod
POSTGRES_USER=chatbot_prod_user
POSTGRES_PASSWORD=SenhaForte123!@#MuitoSegura
DATABASE_URL=postgresql://chatbot_prod_user:SenhaForte123!@#MuitoSegura@postgres:5432/chatbot_prod

# Redis
REDIS_URL=redis://redis:6379

# n8n
N8N_BASIC_AUTH_USER=admin
N8N_BASIC_AUTH_PASSWORD=SenhaForteN8N!@#456
N8N_ENCRYPTION_KEY=chave-encriptacao-n8n-muito-longa-e-segura

# WAHA
WAHA_API_KEY=chave-api-waha-muito-segura-gerar-uuid
WAHA_DASHBOARD_PASSWORD=SenhaForteDashboard!@#789

# Bot
BOT_API_KEY=chave-api-bot-muito-segura-gerar-uuid

# Domínio (para webhooks)
DOMAIN=seu-dominio.com.br
```

**Gerar chaves seguras:**
```bash
# SECRET_KEY do Django
python -c "import secrets; print(secrets.token_urlsafe(50))"

# API Keys
python -c "import uuid; print(uuid.uuid4().hex)"
```

---

## 4. Docker Compose de Produção

Crie `docker-compose.prod.yml`:

```yaml
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    container_name: chatbot-postgres
    restart: always
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      TZ: America/Sao_Paulo
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init:/docker-entrypoint-initdb.d
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10
    networks:
      - internal

  redis:
    image: redis:7-alpine
    container_name: chatbot-redis
    restart: always
    command: redis-server --appendonly yes
    volumes:
      - redisdata:/data
    networks:
      - internal

  backend:
    build:
      context: .
      dockerfile: Dockerfile.prod
    container_name: chatbot-backend
    restart: always
    environment:
      - TZ=America/Sao_Paulo
      - DJANGO_SECRET_KEY=${DJANGO_SECRET_KEY}
      - DJANGO_DEBUG=${DJANGO_DEBUG}
      - DJANGO_ALLOWED_HOSTS=${DJANGO_ALLOWED_HOSTS}
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - BOT_API_KEY=${BOT_API_KEY}
    volumes:
      - static_files:/app/staticfiles
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    networks:
      - internal

  n8n:
    image: n8nio/n8n:latest
    container_name: chatbot-n8n
    restart: always
    environment:
      - TZ=America/Sao_Paulo
      - N8N_HOST=n8n
      - N8N_PORT=5678
      - N8N_PROTOCOL=https
      - WEBHOOK_URL=https://${DOMAIN}/n8n
      - N8N_EDITOR_BASE_URL=https://${DOMAIN}/n8n
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=${N8N_BASIC_AUTH_USER}
      - N8N_BASIC_AUTH_PASSWORD=${N8N_BASIC_AUTH_PASSWORD}
      - N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}
      - DB_TYPE=postgresdb
      - DB_POSTGRESDB_HOST=postgres
      - DB_POSTGRESDB_PORT=5432
      - DB_POSTGRESDB_DATABASE=${POSTGRES_DB}
      - DB_POSTGRESDB_USER=${POSTGRES_USER}
      - DB_POSTGRESDB_PASSWORD=${POSTGRES_PASSWORD}
      - QUEUE_BULL_REDIS_HOST=redis
      - QUEUE_BULL_REDIS_PORT=6379
      - N8N_SECURE_COOKIE=true
    volumes:
      - n8ndata:/home/node/.n8n
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started
    networks:
      - internal

  waha:
    image: devlikeapro/waha:latest
    container_name: chatbot-waha
    restart: always
    environment:
      WAHA_API_KEY: ${WAHA_API_KEY}
      WAHA_API_KEY_PLAIN: ${WAHA_API_KEY}
      REDIS_URL: redis://redis:6379
      WAHA_PRINT_QR: "false"
      WHATSAPP_DEFAULT_ENGINE: GOWS
      WAHA_DASHBOARD_ENABLED: "true"
      WAHA_DASHBOARD_USERNAME: admin
      WAHA_DASHBOARD_PASSWORD: ${WAHA_DASHBOARD_PASSWORD}
      WHATSAPP_SWAGGER_ENABLED: "false"
      WHATSAPP_HOOK_URL: http://n8n:5678/webhook/waha-inbound
      WHATSAPP_HOOK_EVENTS: message,session.status
      WHATSAPP_HOOK_RETRIES_POLICY: linear
      WHATSAPP_HOOK_RETRIES_DELAY_SECONDS: "2"
      WHATSAPP_HOOK_RETRIES_ATTEMPTS: "4"
    volumes:
      - wahadata:/data
    depends_on:
      - redis
    networks:
      - internal

  nginx:
    image: nginx:alpine
    container_name: chatbot-nginx
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/ssl:/etc/nginx/ssl:ro
      - static_files:/var/www/static:ro
    depends_on:
      - backend
      - n8n
      - waha
    networks:
      - internal
      - external

networks:
  internal:
    driver: bridge
  external:
    driver: bridge

volumes:
  pgdata:
  redisdata:
  n8ndata:
  wahadata:
  static_files:
```

---

## 5. Dockerfile de Produção

Crie `Dockerfile.prod`:

```dockerfile
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copia código
COPY . .

# Coleta arquivos estáticos
RUN python manage.py collectstatic --noinput

# Expõe porta
EXPOSE 8000

# Comando de produção com Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2", "backend.wsgi:application"]
```

---

## 6. Configuração do Nginx

Crie `nginx/nginx.conf`:

```nginx
events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Logs
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log;

    # Gzip
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

    # Upstream servers
    upstream backend {
        server backend:8000;
    }

    upstream n8n {
        server n8n:5678;
    }

    upstream waha {
        server waha:3000;
    }

    # Redirect HTTP to HTTPS
    server {
        listen 80;
        server_name seu-dominio.com.br www.seu-dominio.com.br;
        return 301 https://$server_name$request_uri;
    }

    # HTTPS Server
    server {
        listen 443 ssl http2;
        server_name seu-dominio.com.br www.seu-dominio.com.br;

        # SSL Certificates (Let's Encrypt)
        ssl_certificate /etc/nginx/ssl/fullchain.pem;
        ssl_certificate_key /etc/nginx/ssl/privkey.pem;

        # SSL Settings
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
        ssl_prefer_server_ciphers off;

        # Security Headers
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;

        # Static files
        location /static/ {
            alias /var/www/static/;
            expires 30d;
        }

        # Django Backend (Painel)
        location / {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # API (rate limited)
        location /api/ {
            limit_req zone=api burst=20 nodelay;
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # n8n
        location /n8n/ {
            rewrite ^/n8n/(.*) /$1 break;
            proxy_pass http://n8n;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }

        # WAHA Dashboard
        location /waha/ {
            rewrite ^/waha/(.*) /$1 break;
            proxy_pass http://waha;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

---

## 7. Atualizar settings.py para Produção

Atualize `backend/settings.py`:

```python
import os

# Security
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'fallback-insecure-key')
DEBUG = os.environ.get('DJANGO_DEBUG', 'False').lower() == 'true'

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost').split(',')

# HTTPS settings
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = '/app/staticfiles'

# Bot API Key from environment
BOT_API_KEY = os.environ.get('BOT_API_KEY', 'default-insecure-key')
```

---

## 8. Certificado SSL (Let's Encrypt)

```bash
# Instala Certbot
sudo apt install certbot

# Gera certificado (pare o nginx primeiro)
sudo certbot certonly --standalone -d seu-dominio.com.br -d www.seu-dominio.com.br

# Copia para a pasta do projeto
sudo cp /etc/letsencrypt/live/seu-dominio.com.br/fullchain.pem ./nginx/ssl/
sudo cp /etc/letsencrypt/live/seu-dominio.com.br/privkey.pem ./nginx/ssl/
sudo chmod 644 ./nginx/ssl/*.pem

# Renovação automática (adicionar ao crontab)
0 0 1 * * certbot renew --quiet && docker-compose -f docker-compose.prod.yml restart nginx
```

---

## 9. Deploy

```bash
# 1. Conecta ao servidor
ssh usuario@seu-servidor

# 2. Cria diretório
sudo mkdir -p /opt/chatbot-agenda
cd /opt/chatbot-agenda

# 3. Copia arquivos (do seu computador local)
scp -r ./* usuario@seu-servidor:/opt/chatbot-agenda/

# 4. Cria o arquivo .env.prod com as variáveis

# 5. Cria diretório para SSL
mkdir -p nginx/ssl

# 6. Build e start
docker-compose -f docker-compose.prod.yml --env-file .env.prod build
docker-compose -f docker-compose.prod.yml --env-file .env.prod up -d

# 7. Executa migrations e cria slots
docker-compose -f docker-compose.prod.yml exec backend python manage.py migrate
docker-compose -f docker-compose.prod.yml exec backend python manage.py criar_slots --dias 60 --pular-sabado

# 8. Verifica logs
docker-compose -f docker-compose.prod.yml logs -f
```

---

## 10. Backup Automático

Crie `scripts/backup.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/opt/chatbot-agenda/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Backup do PostgreSQL
docker-compose -f /opt/chatbot-agenda/docker-compose.prod.yml exec -T postgres \
    pg_dump -U $POSTGRES_USER $POSTGRES_DB | gzip > $BACKUP_DIR/db_$DATE.sql.gz

# Mantém apenas os últimos 7 dias
find $BACKUP_DIR -name "*.gz" -mtime +7 -delete

echo "Backup concluído: db_$DATE.sql.gz"
```

```bash
# Torna executável
chmod +x scripts/backup.sh

# Adiciona ao crontab (backup diário às 3h)
0 3 * * * /opt/chatbot-agenda/scripts/backup.sh
```

---

## 11. Monitoramento

### Verificar status
```bash
docker-compose -f docker-compose.prod.yml ps
```

### Ver logs
```bash
docker-compose -f docker-compose.prod.yml logs -f backend
docker-compose -f docker-compose.prod.yml logs -f n8n
docker-compose -f docker-compose.prod.yml logs -f waha
```

### Reiniciar serviços
```bash
docker-compose -f docker-compose.prod.yml restart backend
```

---

## 12. Checklist de Segurança

- [ ] SECRET_KEY forte e única
- [ ] DEBUG = False
- [ ] ALLOWED_HOSTS configurado
- [ ] HTTPS habilitado
- [ ] Senhas fortes para todos os serviços
- [ ] Firewall configurado (apenas 80, 443, 22)
- [ ] Backup automático configurado
- [ ] Certificado SSL válido
- [ ] Rate limiting habilitado
- [ ] Headers de segurança configurados

---

## 13. URLs em Produção

| Serviço | URL |
|---------|-----|
| Painel | https://seu-dominio.com.br |
| API | https://seu-dominio.com.br/api/ |
| n8n | https://seu-dominio.com.br/n8n/ |
| WAHA | https://seu-dominio.com.br/waha/ |

---

## 14. Troubleshooting

### Erro 502 Bad Gateway
```bash
docker-compose -f docker-compose.prod.yml logs backend
docker-compose -f docker-compose.prod.yml restart backend
```

### Banco não conecta
```bash
docker-compose -f docker-compose.prod.yml exec postgres psql -U $POSTGRES_USER -d $POSTGRES_DB
```

### WAHA não recebe mensagens
1. Verifique se o webhook está configurado: https://seu-dominio.com.br/n8n/webhook/waha-inbound
2. Verifique os logs do WAHA
3. Reconecte a sessão do WhatsApp

### Certificado SSL expirado
```bash
sudo certbot renew
docker-compose -f docker-compose.prod.yml restart nginx
```

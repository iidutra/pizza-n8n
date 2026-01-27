# Arquitetura Técnica - Sistema de Agendamento via WhatsApp

## Visão Geral

Sistema de agendamento conversacional via WhatsApp utilizando arquitetura de microserviços com Django, n8n, Redis e WAHA (WhatsApp HTTP API).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ARQUITETURA GERAL                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────────────┐  │
│   │ WhatsApp │────▶│   WAHA   │────▶│   n8n    │────▶│  Django Backend  │  │
│   │  Usuário │◀────│  (API)   │◀────│(Workflow)│◀────│     (API REST)   │  │
│   └──────────┘     └──────────┘     └──────────┘     └──────────────────┘  │
│                                                              │               │
│                                                              ▼               │
│                                           ┌──────────┐  ┌──────────┐        │
│                                           │  Redis   │  │PostgreSQL│        │
│                                           │ (Estado) │  │  (Dados) │        │
│                                           └──────────┘  └──────────┘        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Stack Tecnológica

| Componente | Tecnologia | Função |
|------------|------------|--------|
| **Backend API** | Django + DRF | API REST, lógica de negócio, painel admin |
| **Banco de Dados** | PostgreSQL | Persistência de dados (slots, agendamentos, pacientes) |
| **Cache/Estado** | Redis | Gerenciamento de estado conversacional do chatbot |
| **WhatsApp API** | WAHA | Envio/recebimento de mensagens WhatsApp |
| **Orquestração** | n8n | Workflow que conecta WAHA ao backend |
| **Containerização** | Docker Compose | Orquestração dos serviços |
| **Web Server** | Nginx (prod) | Proxy reverso, SSL, roteamento |

---

## Estrutura de Diretórios

```
atendimento-n8n/
├── agenda/                          # App Django principal
│   ├── management/
│   │   └── commands/
│   │       └── criar_slots.py       # Comando para criar slots
│   ├── migrations/                  # Migrations do banco
│   ├── static/
│   │   └── css/
│   │       └── dracula.css          # Tema Dracula do painel
│   ├── templates/                   # Templates HTML do painel
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── appointments.html
│   │   └── patients.html
│   ├── admin.py                     # Configuração Django Admin
│   ├── bot_views.py                 # ⭐ CORE: Lógica do chatbot
│   ├── models.py                    # Modelos do banco
│   ├── panel_views.py               # Views do painel web
│   ├── serializers.py               # Serializers DRF
│   ├── urls.py                      # Rotas da API
│   └── views.py                     # Views da API REST
│
├── backend/                         # Configurações Django
│   ├── settings.py                  # Configurações gerais
│   ├── urls.py                      # Rotas principais
│   └── wsgi.py
│
├── docs/                            # Documentação
│   ├── ARQUITETURA_TECNICA.md       # Este arquivo
│   ├── TEMA_DRACULA.md              # Documentação do tema
│   └── DEPLOY_PRODUCAO.md           # Guia de deploy
│
├── nginx/                           # Configuração Nginx (produção)
│   └── nginx.conf
│
├── scripts/                         # Scripts de automação
│   ├── deploy.sh
│   ├── backup.sh
│   └── restore.sh
│
├── docker-compose.yml               # Desenvolvimento
├── docker-compose.prod.yml          # Produção
├── Dockerfile                       # Build desenvolvimento
├── Dockerfile.prod                  # Build produção
├── requirements.txt                 # Dependências Python
└── .env.example                     # Template de variáveis
```

---

## Banco de Dados

### Diagrama ER

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│    patients     │       │  appointments   │       │     slots       │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ id (PK)         │       │ id (PK)         │       │ id (PK)         │
│ name            │◀──────│ patient_id (FK) │       │ starts_at       │
│ phone           │       │ slot_id (FK)    │──────▶│ ends_at         │
│ email           │       │ status          │       │ status          │
│ created_at      │       │ notes           │       │ created_at      │
│ updated_at      │       │ created_at      │       │ updated_at      │
└─────────────────┘       │ updated_at      │       └─────────────────┘
                          └─────────────────┘
```

### Schema SQL

```sql
-- Tabela de Pacientes
CREATE TABLE patients (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    phone VARCHAR(20) UNIQUE NOT NULL,
    email VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabela de Slots (horários disponíveis)
CREATE TABLE slots (
    id SERIAL PRIMARY KEY,
    starts_at TIMESTAMP WITH TIME ZONE NOT NULL,
    ends_at TIMESTAMP WITH TIME ZONE NOT NULL,
    status VARCHAR(20) DEFAULT 'FREE',  -- FREE, BOOKED
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabela de Agendamentos
CREATE TABLE appointments (
    id SERIAL PRIMARY KEY,
    patient_id INTEGER REFERENCES patients(id) ON DELETE CASCADE,
    slot_id INTEGER REFERENCES slots(id) ON DELETE CASCADE,
    status VARCHAR(20) DEFAULT 'PENDING',  -- PENDING, CONFIRMED, CANCELLED
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Índices para performance
CREATE INDEX idx_slots_starts_at ON slots(starts_at);
CREATE INDEX idx_slots_status ON slots(status);
CREATE INDEX idx_appointments_status ON appointments(status);
CREATE INDEX idx_patients_phone ON patients(phone);
```

### Status dos Modelos

| Modelo | Status Possíveis |
|--------|------------------|
| **Slot** | `FREE` (disponível), `BOOKED` (reservado) |
| **Appointment** | `PENDING` (aguardando), `CONFIRMED` (confirmado), `CANCELLED` (cancelado) |

---

## API REST

### Endpoints Principais

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `POST` | `/api/bot/message/` | Recebe mensagens do chatbot (via n8n) |
| `GET` | `/api/slots/` | Lista slots disponíveis |
| `GET` | `/api/slots/available/` | Slots livres para agendamento |
| `POST` | `/api/appointments/` | Cria agendamento |
| `GET` | `/api/appointments/` | Lista agendamentos |
| `POST` | `/api/appointments/{id}/confirm/` | Confirma agendamento |
| `POST` | `/api/appointments/{id}/cancel/` | Cancela agendamento |
| `GET` | `/api/patients/` | Lista pacientes |

### Formato de Requisição do Bot

```json
POST /api/bot/message/
{
    "phone": "5511999999999",
    "message": "Olá, quero agendar uma consulta"
}
```

### Formato de Resposta do Bot

```json
{
    "response": "Olá! Qual é o seu nome?",
    "phone": "5511999999999"
}
```

---

## Gerenciamento de Estado (Redis)

### Estrutura do Estado Conversacional

O Redis armazena o estado de cada conversa usando a chave `conv:{phone}`:

```python
{
    "step": "awaiting_name",           # Etapa atual do fluxo
    "data": {
        "name": "João Silva",          # Dados coletados
        "selected_date": "2026-01-27",
        "selected_slot_id": 15
    },
    "last_interaction": "2026-01-25T18:00:00"
}
```

### Estados do Fluxo (Steps)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FLUXO CONVERSACIONAL                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌───────────┐     ┌─────────────────┐     ┌──────────────────────────┐   │
│   │  welcome  │────▶│  awaiting_name  │────▶│  awaiting_menu_choice    │   │
│   └───────────┘     └─────────────────┘     └──────────────────────────┘   │
│                                                          │                   │
│                     ┌────────────────────────────────────┼──────────────┐   │
│                     │                                    │              │   │
│                     ▼                                    ▼              ▼   │
│   ┌─────────────────────┐   ┌───────────────────┐  ┌──────────────────┐   │
│   │ awaiting_date_choice│   │  awaiting_cancel  │  │ show_appointments│   │
│   └─────────────────────┘   └───────────────────┘  └──────────────────┘   │
│              │                                                              │
│              ▼                                                              │
│   ┌─────────────────────┐                                                   │
│   │ awaiting_slot_choice│                                                   │
│   └─────────────────────┘                                                   │
│              │                                                              │
│              ▼                                                              │
│   ┌─────────────────────┐                                                   │
│   │awaiting_confirmation│────▶ Agendamento Criado                          │
│   └─────────────────────┘                                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Funções Redis no Código

```python
import redis
import json

redis_client = redis.Redis(host='redis', port=6379, db=0)
CONVERSATION_TTL = 3600  # 1 hora de expiração

def get_conversation_state(phone: str) -> dict:
    """Recupera estado da conversa"""
    key = f"conv:{phone}"
    data = redis_client.get(key)
    if data:
        return json.loads(data)
    return {"step": "welcome", "data": {}}

def set_conversation_state(phone: str, state: dict):
    """Salva estado da conversa"""
    key = f"conv:{phone}"
    redis_client.setex(key, CONVERSATION_TTL, json.dumps(state))

def clear_conversation_state(phone: str):
    """Limpa estado (após conclusão ou timeout)"""
    key = f"conv:{phone}"
    redis_client.delete(key)
```

---

## Lógica do Chatbot

### Arquivo Principal: `bot_views.py`

```python
# Estrutura principal do handler de mensagens

@api_view(['POST'])
def bot_message(request):
    phone = request.data.get('phone')
    message = request.data.get('message', '').strip()

    # 1. Normaliza telefone
    phone = normalize_phone(phone)

    # 2. Recupera estado atual
    state = get_conversation_state(phone)
    current_step = state.get("step", "welcome")

    # 3. Processa baseado no step atual
    if current_step == "welcome":
        response = handle_welcome(phone, message, state)
    elif current_step == "awaiting_name":
        response = handle_name(phone, message, state)
    elif current_step == "awaiting_menu_choice":
        response = handle_menu(phone, message, state)
    # ... outros steps

    return Response({"response": response, "phone": phone})
```

### Configuração do Consultório

```python
CONSULTORIO_CONFIG = {
    "nome_medica": "Dra. Letícia Telles",
    "especialidade": "Clínica Geral",
    "foco": "envelhecimento saudável e longevidade",
    "endereco": "Rua Example, 123 - Centro",
    "valor_consulta": "R$ 300,00",
    "duracao_consulta": "45 minutos a 1 hora",
    "telefone": "(11) 99999-9999",
    "aceita_convenio": False,
}
```

---

## Integração n8n

### Workflow de Recebimento

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ WAHA Trigger │────▶│  HTTP Request│────▶│ WAHA Send    │
│ (Webhook)    │     │  (POST API)  │     │ (Response)   │
└──────────────┘     └──────────────┘     └──────────────┘
```

### Configuração do Webhook WAHA

1. **Trigger**: Webhook que recebe mensagens do WAHA
2. **Extração**: Obtém telefone e mensagem do payload
3. **HTTP Request**: Envia para Django API (`POST /api/bot/message/`)
4. **Resposta**: Envia resposta via WAHA para o usuário

### Payload WAHA (Entrada)

```json
{
    "event": "message",
    "payload": {
        "from": "5511999999999@c.us",
        "body": "Olá, quero agendar",
        "fromMe": false
    }
}
```

### Extração do Telefone (LID Format)

```python
def normalize_phone(phone: str) -> str:
    """
    Normaliza telefone removendo sufixos WAHA
    Entrada: "5511999999999@c.us" ou "5511999999999@lid"
    Saída: "5511999999999"
    """
    if not phone:
        return ""

    # Remove sufixos do WAHA
    phone = phone.split('@')[0]
    phone = phone.split(':')[0]

    # Remove caracteres não numéricos
    phone = re.sub(r'\D', '', phone)

    return phone
```

---

## Docker Compose

### Desenvolvimento (`docker-compose.yml`)

```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: chatbot_user
      POSTGRES_PASSWORD: chatbot_pass
      POSTGRES_DB: chatbot
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  backend:
    build: .
    command: python manage.py runserver 0.0.0.0:8000
    volumes:
      - .:/app
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis
    environment:
      - DATABASE_URL=postgres://chatbot_user:chatbot_pass@postgres:5432/chatbot
      - REDIS_URL=redis://redis:6379/0

  n8n:
    image: n8nio/n8n
    ports:
      - "5678:5678"
    volumes:
      - n8n_data:/home/node/.n8n
    environment:
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=admin
      - N8N_BASIC_AUTH_PASSWORD=admin123

  waha:
    image: devlikeapro/waha
    ports:
      - "3000:3000"
    environment:
      - WHATSAPP_HOOK_URL=http://n8n:5678/webhook/waha

volumes:
  postgres_data:
  n8n_data:
```

### Portas dos Serviços

| Serviço | Porta | URL Local |
|---------|-------|-----------|
| Backend Django | 8000 | http://localhost:8000 |
| n8n | 5678 | http://localhost:5678 |
| WAHA | 3000 | http://localhost:3000 |
| PostgreSQL | 5432 | localhost:5432 |
| Redis | 6379 | localhost:6379 |

---

## Comandos Úteis

### Desenvolvimento

```bash
# Subir todos os serviços
docker-compose up -d

# Ver logs
docker-compose logs -f backend

# Acessar shell do Django
docker-compose exec backend python manage.py shell

# Criar migrations
docker-compose exec backend python manage.py makemigrations

# Aplicar migrations
docker-compose exec backend python manage.py migrate

# Criar slots de agendamento
docker-compose exec backend python manage.py criar_slots --dias 30

# Reiniciar backend após mudanças
docker-compose restart backend
```

### Banco de Dados

```bash
# Acessar PostgreSQL
docker-compose exec postgres psql -U chatbot_user -d chatbot

# Limpar dados
docker-compose exec postgres psql -U chatbot_user -d chatbot \
    -c "DELETE FROM appointments; DELETE FROM slots; DELETE FROM patients;"

# Backup
docker-compose exec postgres pg_dump -U chatbot_user chatbot > backup.sql

# Restore
docker-compose exec -T postgres psql -U chatbot_user chatbot < backup.sql
```

### Redis

```bash
# Acessar Redis CLI
docker-compose exec redis redis-cli

# Ver todas as conversas ativas
docker-compose exec redis redis-cli KEYS "conv:*"

# Ver estado de uma conversa específica
docker-compose exec redis redis-cli GET "conv:5511999999999"

# Limpar todas as conversas
docker-compose exec redis redis-cli FLUSHDB
```

---

## Adaptação para Outros Projetos

### Exemplo: Sistema de Matrícula de Alunos

Para adaptar este sistema para matrículas em centro de treinamento:

#### 1. Modificar Modelos

```python
# models.py

class Modalidade(models.Model):
    """Modalidades oferecidas (Judô, Natação, etc)"""
    nome = models.CharField(max_length=100)
    descricao = models.TextField()
    valor_mensal = models.DecimalField(max_digits=10, decimal_places=2)
    idade_minima = models.IntegerField(default=0)
    idade_maxima = models.IntegerField(default=99)
    ativo = models.BooleanField(default=True)

class Turma(models.Model):
    """Turmas disponíveis por modalidade"""
    modalidade = models.ForeignKey(Modalidade, on_delete=models.CASCADE)
    nome = models.CharField(max_length=100)  # "Judô Infantil Manhã"
    dia_semana = models.CharField(max_length=50)  # "Segunda e Quarta"
    horario = models.CharField(max_length=50)  # "08:00 - 09:00"
    vagas_total = models.IntegerField()
    vagas_disponiveis = models.IntegerField()

class Aluno(models.Model):
    """Alunos matriculados"""
    nome = models.CharField(max_length=255)
    telefone = models.CharField(max_length=20, unique=True)
    email = models.EmailField(blank=True)
    data_nascimento = models.DateField()
    responsavel = models.CharField(max_length=255, blank=True)  # Para menores
    telefone_responsavel = models.CharField(max_length=20, blank=True)

class Matricula(models.Model):
    """Matrículas realizadas"""
    aluno = models.ForeignKey(Aluno, on_delete=models.CASCADE)
    turma = models.ForeignKey(Turma, on_delete=models.CASCADE)
    status = models.CharField(max_length=20)  # PENDENTE, ATIVA, CANCELADA
    data_inicio = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
```

#### 2. Novo Fluxo Conversacional

```
welcome → awaiting_name → awaiting_birth_date →
    → show_modalidades → awaiting_modalidade_choice →
    → show_turmas → awaiting_turma_choice →
    → awaiting_confirmation → matricula_criada
```

#### 3. Configuração do Centro

```python
CENTRO_CONFIG = {
    "nome": "Centro de Treinamento XYZ",
    "endereco": "Rua dos Esportes, 100",
    "telefone": "(11) 3333-3333",
    "horario_funcionamento": "06:00 às 22:00",
    "modalidades": ["Judô", "Natação", "Musculação", "Pilates"],
}
```

#### 4. Handlers Específicos

```python
def _responder_escolha_modalidade(self, phone, message, state):
    """Processa escolha de modalidade e mostra turmas"""
    modalidades = Modalidade.objects.filter(ativo=True)

    # Encontra modalidade escolhida
    escolha = int(message) - 1
    modalidade = modalidades[escolha]

    # Busca turmas disponíveis
    turmas = Turma.objects.filter(
        modalidade=modalidade,
        vagas_disponiveis__gt=0
    )

    # Monta resposta com turmas
    response = f"*{modalidade.nome}*\n\n"
    response += f"Valor: R$ {modalidade.valor_mensal}/mês\n\n"
    response += "Turmas disponíveis:\n\n"

    for i, turma in enumerate(turmas, 1):
        response += f"{i}. {turma.nome}\n"
        response += f"   {turma.dia_semana} - {turma.horario}\n"
        response += f"   Vagas: {turma.vagas_disponiveis}\n\n"

    # Atualiza estado
    state["step"] = "awaiting_turma_choice"
    state["data"]["modalidade_id"] = modalidade.id
    set_conversation_state(phone, state)

    return response
```

---

## Checklist para Novo Projeto

- [ ] Clonar estrutura base
- [ ] Definir modelos de dados específicos
- [ ] Criar migrations
- [ ] Configurar variáveis de ambiente
- [ ] Adaptar `CONSULTORIO_CONFIG` para novo contexto
- [ ] Reescrever fluxo em `bot_views.py`
- [ ] Criar comando de população de dados (similar a `criar_slots`)
- [ ] Adaptar templates do painel
- [ ] Configurar workflow n8n
- [ ] Testar fluxo completo
- [ ] Deploy em produção

---

## Referências

- [Django REST Framework](https://www.django-rest-framework.org/)
- [WAHA - WhatsApp HTTP API](https://waha.devlike.pro/)
- [n8n - Workflow Automation](https://n8n.io/)
- [Redis Documentation](https://redis.io/docs/)
- [Docker Compose](https://docs.docker.com/compose/)

---

*Documentação criada em Janeiro/2026*
*Sistema de Agendamento via WhatsApp v1.0*

# Pastoral dos Coroinhas

Sistema paroquial para gestão de coroinhas — escalas, presenças, formações e portal das famílias.

## Stack

- **Backend:** Django 5 + DRF + JWT + PostgreSQL + Redis
- **Frontend:** Next.js 15 + TypeScript + Tailwind
- **Infra:** Docker Compose

## Início rápido (sem Docker — recomendado no Windows)

```powershell
cd pastoral-coroinhas
Copy-Item .env.local.example .env
.\scripts\dev-local.ps1
```

Em **outro terminal**:

```powershell
cd pastoral-coroinhas\frontend
npm install
npm run dev
```

- Frontend: http://localhost:3000
- API: http://localhost:8000/api/v1

**Criar coordenador:**

```powershell
.\scripts\dev-local.ps1 -CriarCoordenador -Email coord@paroquia.org -Senha admin123
```

**Dados e usuários de demonstração:**

```powershell
.\scripts\dev-local.ps1 -SeedDemo
```

| Perfil | Login | Senha | Destino |
|--------|-------|-------|---------|
| Coordenador | `coord@paroquia.org` | `admin123` | Dashboard |
| Secretário | `secretario@paroquia.org` | `demo123` | Dashboard |
| Padre | `padre@paroquia.org` | `demo123` | Dashboard (somente leitura) |
| Pai | CPF `111.444.777-35` | `demo123` | Portal |
| Coroinha | CPF `529.982.247-25` | `demo123` | Portal |

Login único: informe **CPF ou e-mail** na mesma tela — o sistema detecta automaticamente.

Usa SQLite + cache em memória — não precisa de PostgreSQL, Redis nem Docker.

---

## Docker (quando Docker Desktop estiver ok)

```powershell
cd pastoral-coroinhas
Copy-Item .env.example .env
docker compose up --build
```

### Docker Desktop com erro 500

Se aparecer `Docker Desktop is unable to start` ou `500 Internal Server Error`:

1. Abra **Docker Desktop** e aguarde ficar verde (Running)
2. Se não subir: **Settings → Troubleshoot → Restart Docker Desktop**
3. Reinicie o PC se persistir (WSL2 às vezes trava)
4. Enquanto isso, use o modo local acima (`.\scripts\dev-local.ps1`)


## API principal

| Endpoint | Descrição |
|----------|-----------|
| `POST /api/v1/auth/login` | Login unificado (CPF ou e-mail + senha) |
| `POST /api/v1/auth/recuperar-senha` | CPF + data nascimento + nova senha |
| `GET /api/v1/relatorios/escala-mes?ano=&mes=&formato=pdf` | Exportar escala do mês (PDF) |
| `POST /api/v1/inscricoes/publica` | Inscrição online |
| `GET /api/v1/portal/filhos` | Filhos do pai logado |
| `GET /api/v1/portal/coroinhas/{id}/resumo` | Portal família |
| `GET /api/v1/dashboard/stats` | KPIs staff |

## Estrutura

```
pastoral-coroinhas/
├── backend/
│   ├── apps/identity/       # Auth, Usuario, JWT
│   ├── apps/membership/     # Coroinha, Responsavel, Inscricao, Portal
│   ├── apps/scheduling/     # Missas, Escalas, sorteio
│   ├── apps/attendance/     # Presença
│   ├── apps/training/       # Formações
│   ├── apps/communication/  # Mensagens (simulação)
│   └── apps/content/        # Notícias, Documentos
├── frontend/                # Next.js
├── docker-compose.yml
└── .cursor/rules/           # Regras Cursor
```

**Dados de demonstração:**

```powershell
.\scripts\dev-local.ps1 -SeedDemo
```

Cria coroinhas, escalas e usuários Padre / Pai / Coroinha (ver tabela acima).

## Próximos passos (produção)

- [ ] Testes automatizados (pytest + frontend)
- [ ] Pipeline CI/CD (GitLab)
- [ ] Docker estável em produção
- [ ] WhatsApp/e-mail real (hoje é simulação)
- [ ] Rate limit na recuperação de senha
- [ ] Observabilidade (Prometheus + Grafana)

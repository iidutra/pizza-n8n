# Tema Dracula - Documentação

Tema escuro baseado na paleta Dracula, otimizado para painéis administrativos e dashboards.

---

## Paleta de Cores

### Cores de Fundo
| Variável | Cor | Hex | Uso |
|----------|-----|-----|-----|
| `--bg-primary` | ![#282a36](https://via.placeholder.com/15/282a36/282a36.png) | `#282a36` | Fundo principal da página |
| `--bg-secondary` | ![#1e1f29](https://via.placeholder.com/15/1e1f29/1e1f29.png) | `#1e1f29` | Header, footer |
| `--bg-tertiary` | ![#343746](https://via.placeholder.com/15/343746/343746.png) | `#343746` | Hover, inputs |
| `--bg-card` | ![#21222c](https://via.placeholder.com/15/21222c/21222c.png) | `#21222c` | Cards, tabelas |

### Cores de Texto
| Variável | Cor | Hex | Uso |
|----------|-----|-----|-----|
| `--text-primary` | ![#f8f8f2](https://via.placeholder.com/15/f8f8f2/f8f8f2.png) | `#f8f8f2` | Texto principal |
| `--text-secondary` | ![#6272a4](https://via.placeholder.com/15/6272a4/6272a4.png) | `#6272a4` | Texto secundário, labels |
| `--text-muted` | ![#44475a](https://via.placeholder.com/15/44475a/44475a.png) | `#44475a` | Texto desabilitado |

### Cores de Destaque (Accent)
| Variável | Cor | Hex | Uso |
|----------|-----|-----|-----|
| `--accent-purple` | ![#bd93f9](https://via.placeholder.com/15/bd93f9/bd93f9.png) | `#bd93f9` | Principal, links, totais |
| `--accent-pink` | ![#ff79c6](https://via.placeholder.com/15/ff79c6/ff79c6.png) | `#ff79c6` | Gradientes, destaques |
| `--accent-green` | ![#50fa7b](https://via.placeholder.com/15/50fa7b/50fa7b.png) | `#50fa7b` | Sucesso, confirmado |
| `--accent-cyan` | ![#8be9fd](https://via.placeholder.com/15/8be9fd/8be9fd.png) | `#8be9fd` | Informação, datas |
| `--accent-yellow` | ![#f1fa8c](https://via.placeholder.com/15/f1fa8c/f1fa8c.png) | `#f1fa8c` | Aviso, pendente |
| `--accent-orange` | ![#ffb86c](https://via.placeholder.com/15/ffb86c/ffb86c.png) | `#ffb86c` | Alerta, não compareceu |
| `--accent-red` | ![#ff5555](https://via.placeholder.com/15/ff5555/ff5555.png) | `#ff5555` | Erro, cancelado |

### Outras
| Variável | Valor | Uso |
|----------|-------|-----|
| `--border-color` | `#44475a` | Bordas de cards e inputs |
| `--shadow` | `0 4px 6px rgba(0,0,0,0.3)` | Sombras |
| `--radius` | `8px` | Border radius padrão |

---

## Componentes

### 1. Cards de Estatísticas

```html
<div class="stats-grid">
    <div class="stat-card pending">
        <div class="stat-value">12</div>
        <div class="stat-label">Pendentes</div>
    </div>
    <div class="stat-card confirmed">
        <div class="stat-value">45</div>
        <div class="stat-label">Confirmados</div>
    </div>
    <div class="stat-card canceled">
        <div class="stat-value">3</div>
        <div class="stat-label">Cancelados</div>
    </div>
    <div class="stat-card total">
        <div class="stat-value">60</div>
        <div class="stat-label">Total</div>
    </div>
</div>
```

**Classes disponíveis:** `pending` (amarelo), `confirmed` (verde), `canceled` (vermelho), `total` (roxo)

---

### 2. Tabelas

```html
<div class="table-container">
    <div class="table-header">
        <div class="table-title">
            <span>📋</span> Título da Tabela
        </div>
        <button class="btn btn-secondary btn-sm">Ação</button>
    </div>

    <table>
        <thead>
            <tr>
                <th>Coluna 1</th>
                <th>Coluna 2</th>
                <th>Status</th>
                <th>Ações</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Dado 1</td>
                <td>Dado 2</td>
                <td>
                    <span class="status-badge confirmed">
                        <span class="status-dot"></span>
                        Confirmado
                    </span>
                </td>
                <td>
                    <div class="actions">
                        <button class="action-btn confirm">✓</button>
                        <button class="action-btn cancel">✕</button>
                    </div>
                </td>
            </tr>
        </tbody>
    </table>

    <!-- Paginação -->
    <div class="pagination-container">
        <div class="pagination-info">Mostrando 1 a 10 de 100</div>
        <div class="pagination">
            <a href="#" class="page-link disabled">«</a>
            <a href="#" class="page-link active">1</a>
            <a href="#" class="page-link">2</a>
            <a href="#" class="page-link">3</a>
            <a href="#" class="page-link">»</a>
        </div>
    </div>
</div>
```

---

### 3. Status Badges

```html
<span class="status-badge pending">
    <span class="status-dot"></span>
    Pendente
</span>

<span class="status-badge confirmed">
    <span class="status-dot"></span>
    Confirmado
</span>

<span class="status-badge canceled">
    <span class="status-dot"></span>
    Cancelado
</span>

<span class="status-badge no_show">
    <span class="status-dot"></span>
    Não Compareceu
</span>
```

---

### 4. Botões

```html
<!-- Botões principais -->
<button class="btn btn-primary">Primário</button>
<button class="btn btn-secondary">Secundário</button>
<button class="btn btn-success">Sucesso</button>
<button class="btn btn-danger">Perigo</button>
<button class="btn btn-warning">Aviso</button>

<!-- Botão pequeno -->
<button class="btn btn-primary btn-sm">Pequeno</button>

<!-- Botão com ícone -->
<button class="btn btn-primary">
    🔍 Buscar
</button>
```

---

### 5. Filtros

```html
<form class="filters-bar">
    <div class="filter-group">
        <label class="filter-label">Status</label>
        <select class="filter-select">
            <option value="">Todos</option>
            <option value="pending">Pendente</option>
            <option value="confirmed">Confirmado</option>
        </select>
    </div>

    <div class="filter-group">
        <label class="filter-label">Data</label>
        <input type="date" class="filter-input">
    </div>

    <div class="filter-group">
        <label class="filter-label">Buscar</label>
        <input type="text" class="filter-input" placeholder="Digite...">
    </div>

    <div class="filter-group" style="align-self: flex-end;">
        <button type="submit" class="btn btn-primary">🔍 Filtrar</button>
    </div>
</form>
```

---

### 6. Header com Navegação

```html
<header class="header">
    <div class="header-content">
        <div class="logo">
            <div class="logo-icon">📅</div>
            <h1>Nome do Sistema</h1>
        </div>
        <nav class="header-nav">
            <a href="#" class="nav-link active">Dashboard</a>
            <a href="#" class="nav-link">Página 2</a>
            <a href="#" class="nav-link">Página 3</a>
        </nav>
    </div>
</header>
```

---

### 7. Toast Notifications

```html
<div class="toast-container" id="toastContainer"></div>

<script>
function showToast(message, type = 'success') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;

    const icons = {
        success: '✓',
        error: '✕',
        warning: '⚠'
    };

    toast.innerHTML = `
        <span class="toast-icon">${icons[type]}</span>
        <span class="toast-message">${message}</span>
        <button class="toast-close" onclick="this.parentElement.remove()">×</button>
    `;

    container.appendChild(toast);
    setTimeout(() => toast.remove(), 5000);
}

// Uso:
showToast('Operação realizada com sucesso!', 'success');
showToast('Erro ao processar!', 'error');
showToast('Atenção!', 'warning');
</script>
```

---

### 8. Modal

```html
<div class="modal-overlay" id="modal">
    <div class="modal">
        <div class="modal-header">
            <h3 class="modal-title">Título do Modal</h3>
            <button class="modal-close" onclick="closeModal()">×</button>
        </div>
        <div class="modal-body">
            <div class="form-group">
                <label>Campo</label>
                <input type="text" placeholder="Digite...">
            </div>
        </div>
        <div class="modal-footer">
            <button class="btn btn-secondary" onclick="closeModal()">Cancelar</button>
            <button class="btn btn-primary">Salvar</button>
        </div>
    </div>
</div>

<script>
function openModal() {
    document.getElementById('modal').classList.add('active');
}
function closeModal() {
    document.getElementById('modal').classList.remove('active');
}
</script>
```

---

### 9. Estado Vazio

```html
<div class="empty-state">
    <div class="empty-icon">📭</div>
    <h3 class="empty-title">Nenhum dado encontrado</h3>
    <p class="empty-text">Tente ajustar os filtros ou aguarde novos registros.</p>
    <button class="btn btn-primary">Ação</button>
</div>
```

---

### 10. Informações de Paciente/Usuário

```html
<div class="patient-info">
    <span class="patient-name">João da Silva</span>
    <span class="patient-phone">+55 11 99999-9999</span>
</div>
```

---

### 11. Informações de Data

```html
<div class="date-info">
    <span class="date-day">25/01/2026</span>
    <span class="date-time">14:30</span>
</div>
```

---

## Classes Utilitárias

```css
.text-center { text-align: center; }
.text-right { text-align: right; }
.mt-10 { margin-top: 10px; }
.mt-20 { margin-top: 20px; }
.mb-10 { margin-bottom: 10px; }
.mb-20 { margin-bottom: 20px; }
.flex { display: flex; }
.items-center { align-items: center; }
.justify-between { justify-content: space-between; }
.gap-10 { gap: 10px; }
.gap-20 { gap: 20px; }
```

---

## Integração em Outros Projetos

### Django

1. Copie `dracula.css` para `seu_app/static/css/`
2. No template base:

```html
{% load static %}
<link rel="stylesheet" href="{% static 'css/dracula.css' %}">
```

### HTML Puro

```html
<link rel="stylesheet" href="css/dracula.css">
```

### Flask

```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/dracula.css') }}">
```

---

## Customização

Para personalizar as cores, edite as variáveis CSS no `:root`:

```css
:root {
    /* Mude aqui para personalizar */
    --accent-purple: #bd93f9;
    --accent-pink: #ff79c6;
    /* ... */
}
```

---

## Fontes Recomendadas

O tema usa a fonte **Inter** do Google Fonts:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
```

---

## Responsividade

O tema é responsivo por padrão:
- **Desktop**: Layout completo
- **Tablet** (< 768px): Filtros empilhados, tabela com scroll horizontal
- **Mobile** (< 480px): Cards em coluna única

---

## Licença

Livre para uso em projetos pessoais e comerciais.
Baseado na paleta [Dracula Theme](https://draculatheme.com/).

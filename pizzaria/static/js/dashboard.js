// Utility function to get CSRF token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Modal functions
function openModal(modalId) {
    document.getElementById(modalId).classList.add('active');
}

function closeModal() {
    document.querySelectorAll('.modal').forEach(modal => {
        modal.classList.remove('active');
    });
}

// Close modal on escape key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeModal();
    }
});

// Close modal on click outside
document.querySelectorAll('.modal').forEach(modal => {
    modal.addEventListener('click', function(e) {
        if (e.target === this) {
            closeModal();
        }
    });
});

// Auto-refresh dashboard every 30 seconds
if (window.location.pathname === '/' || window.location.pathname === '/dashboard/') {
    setInterval(function() {
        location.reload();
    }, 30000);
}

// Notification sound for new orders
let lastOrderCount = -1;  // -1 indica que ainda não carregou
let lastAwaitingCount = 0;
let audioContext = null;
let audioEnabled = false;

// Inicializa AudioContext após interação do usuário
function initAudio() {
    if (audioContext) return;
    try {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
        audioEnabled = true;
        updateBellStatus();
        console.log('Audio habilitado - som vai tocar quando chegar pedido');
    } catch (e) {
        console.log('Erro ao inicializar audio:', e);
    }
}

// Habilita audio no primeiro clique/toque em QUALQUER lugar da página
document.addEventListener('click', initAudio, { once: true });
document.addEventListener('touchstart', initAudio, { once: true });
document.addEventListener('keydown', initAudio, { once: true });

// Clique no sininho ativa notificações
function toggleNotifications() {
    initAudio();
    requestNotificationPermission();

    // Toca som e avisa
    setTimeout(() => {
        playNotificationSound(true);
        showToast('Notificações ativadas! Você será avisado quando chegar pedido 🔔', 'success');
    }, 100);
}

// Atualiza visual do sininho
function updateBellStatus() {
    const bell = document.getElementById('notificationBell');
    if (!bell) return;

    if (audioEnabled) {
        bell.classList.add('active');
        bell.title = 'Avisos ativados! Você será notificado de novos pedidos';
    } else {
        bell.classList.remove('active');
        bell.title = 'Clique para ativar avisos de novos pedidos';
    }
}

// Atualiza badge do sininho com contagem
function updateBellBadge(count) {
    const badge = document.getElementById('bellBadge');
    const bell = document.getElementById('notificationBell');
    if (!badge || !bell) return;

    if (count > 0) {
        badge.textContent = count;
        badge.style.display = 'block';
        bell.classList.add('ringing');

        // Para de balançar depois de 3 segundos
        setTimeout(() => {
            bell.classList.remove('ringing');
        }, 3000);
    } else {
        badge.style.display = 'none';
        bell.classList.remove('ringing');
    }
}

// Som de notificação mais audível (beep repetido)
function playNotificationSound(force = false) {
    // Tenta usar AudioContext
    if (audioContext && audioEnabled) {
        try {
            // Resume se estiver suspenso
            if (audioContext.state === 'suspended') {
                audioContext.resume();
            }

            function beep(frequency, duration, time) {
                const oscillator = audioContext.createOscillator();
                const gainNode = audioContext.createGain();
                oscillator.connect(gainNode);
                gainNode.connect(audioContext.destination);
                oscillator.frequency.value = frequency;
                oscillator.type = 'sine';
                gainNode.gain.setValueAtTime(0.8, time);  // Volume mais alto
                gainNode.gain.exponentialRampToValueAtTime(0.01, time + duration);
                oscillator.start(time);
                oscillator.stop(time + duration);
            }

            // Toca 5 beeps mais intensos
            const now = audioContext.currentTime;
            beep(880, 0.15, now);
            beep(988, 0.15, now + 0.2);
            beep(880, 0.15, now + 0.4);
            beep(988, 0.15, now + 0.6);
            beep(1047, 0.3, now + 0.8);
            console.log('Som tocado!');
        } catch (e) {
            console.log('Erro ao tocar som:', e);
        }
    } else {
        console.log('Audio não habilitado ainda - clique na página para ativar');
    }

    // Também envia notificação do navegador se permitido
    if (Notification.permission === 'granted') {
        try {
            new Notification('🍕 Novo Pedido!', {
                body: 'Um novo pedido chegou na pizzaria!',
                icon: '/static/img/pizza-icon.png',
                tag: 'new-order',
                requireInteraction: true
            });
        } catch (e) {
            console.log('Erro na notificação:', e);
        }
    }
}

// Pede permissão para notificações
function requestNotificationPermission() {
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission().then(permission => {
            console.log('Permissão de notificação:', permission);
        });
    }
}

// Mostra alerta visual de novo pedido
function showNewOrderAlert(count) {
    // Remove alerta anterior se existir
    const existingAlert = document.getElementById('newOrderAlert');
    if (existingAlert) existingAlert.remove();

    const alert = document.createElement('div');
    alert.id = 'newOrderAlert';
    alert.innerHTML = `
        <div style="
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: linear-gradient(135deg, #ff5555, #ff79c6);
            color: white;
            padding: 15px 30px;
            border-radius: 10px;
            font-size: 1.2rem;
            font-weight: bold;
            z-index: 9999;
            box-shadow: 0 4px 20px rgba(255,85,85,0.5);
            animation: pulse 1s infinite;
            cursor: pointer;
        " onclick="this.parentElement.remove(); location.reload();">
            🔔 NOVO PEDIDO! (${count} aguardando) - Clique para atualizar
        </div>
    `;
    document.body.appendChild(alert);

    // Remove após 10 segundos
    setTimeout(() => {
        if (document.getElementById('newOrderAlert')) {
            document.getElementById('newOrderAlert').remove();
        }
    }, 10000);
}

function checkNewOrders() {
    const newOrdersBadge = document.querySelector('.kanban-column.new .badge');
    const awaitingBadge = document.querySelector('.kanban-column.awaiting .badge');

    if (newOrdersBadge) {
        const currentCount = parseInt(newOrdersBadge.textContent) || 0;
        const awaitingCount = awaitingBadge ? parseInt(awaitingBadge.textContent) || 0 : 0;
        const totalCount = currentCount + awaitingCount;

        // Atualiza badge do sininho
        updateBellBadge(totalCount);

        // Na primeira carga, apenas salva os valores
        if (lastOrderCount === -1) {
            lastOrderCount = currentCount;
            lastAwaitingCount = awaitingCount;
            return;
        }

        // Verifica se há novos pedidos ou novos aguardando pagamento
        if (currentCount > lastOrderCount || awaitingCount > lastAwaitingCount) {
            playNotificationSound();
            showNewOrderAlert(totalCount);
        }

        lastOrderCount = currentCount;
        lastAwaitingCount = awaitingCount;
    }
}

// Verifica novos pedidos a cada 15 segundos via AJAX
function pollNewOrders() {
    fetch('/ajax/order-counts/')
        .then(response => response.json())
        .then(data => {
            const currentNew = data.new || 0;
            const currentAwaiting = data.awaiting_payment || 0;
            const totalNew = currentNew + currentAwaiting;

            // Atualiza badge do sininho
            updateBellBadge(totalNew);

            // Na primeira carga, apenas salva os valores
            if (lastOrderCount === -1) {
                lastOrderCount = currentNew;
                lastAwaitingCount = currentAwaiting;
                return;
            }

            const lastTotal = lastOrderCount + lastAwaitingCount;

            if (totalNew > lastTotal) {
                console.log(`Novo pedido detectado! ${lastTotal} -> ${totalNew}`);
                playNotificationSound();
                showNewOrderAlert(totalNew);
                // Recarrega a página para mostrar novos pedidos
                setTimeout(() => location.reload(), 2000);
            }

            lastOrderCount = currentNew;
            lastAwaitingCount = currentAwaiting;
        })
        .catch(err => console.log('Erro ao verificar pedidos:', err));
}

// Initial check e polling
document.addEventListener('DOMContentLoaded', function() {
    // Atualiza visual do sininho
    updateBellStatus();

    // Carrega contagem inicial
    checkNewOrders();

    // Pede permissão de notificação automaticamente
    requestNotificationPermission();

    // Poll a cada 10 segundos para detectar novos pedidos mais rápido
    setInterval(pollNewOrders, 10000);

    // Mostra aviso se áudio não estiver habilitado
    setTimeout(() => {
        if (!audioEnabled) {
            showToast('Clique no 🔔 para ativar avisos de novos pedidos', 'info');
        }
    }, 2000);
});

// Adiciona animação de pulse
const pulseStyle = document.createElement('style');
pulseStyle.textContent = `
    @keyframes pulse {
        0% { transform: translateX(-50%) scale(1); }
        50% { transform: translateX(-50%) scale(1.05); }
        100% { transform: translateX(-50%) scale(1); }
    }
`;
document.head.appendChild(pulseStyle);

// Format currency
function formatCurrency(value) {
    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL'
    }).format(value);
}

// Format time ago
function formatTimeAgo(date) {
    const now = new Date();
    const diff = now - new Date(date);
    const minutes = Math.floor(diff / 60000);

    if (minutes < 1) return 'agora';
    if (minutes < 60) return `${minutes}min atras`;

    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h atras`;

    const days = Math.floor(hours / 24);
    return `${days}d atras`;
}

// Highlight urgent orders (more than 30 minutes)
document.addEventListener('DOMContentLoaded', function() {
    document.querySelectorAll('.order-card').forEach(card => {
        const timeElement = card.querySelector('.order-time');
        if (timeElement) {
            const text = timeElement.textContent;
            const match = text.match(/(\d+)/);
            if (match) {
                const minutes = parseInt(match[1]);
                if (text.includes('min') && minutes > 30) {
                    card.style.borderLeft = '3px solid var(--accent-red)';
                }
            }
        }
    });
});

// Toast notification
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `alert alert-${type}`;
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 9999;
        min-width: 300px;
        animation: slideIn 0.3s ease;
    `;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Add CSS for animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from { transform: translateX(100%); opacity: 0; }
        to { transform: translateX(0); opacity: 1; }
    }
    @keyframes slideOut {
        from { transform: translateX(0); opacity: 1; }
        to { transform: translateX(100%); opacity: 0; }
    }
`;
document.head.appendChild(style);

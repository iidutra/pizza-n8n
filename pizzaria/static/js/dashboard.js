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

// Notification sound for new orders (optional)
let lastOrderCount = 0;

function checkNewOrders() {
    const newOrdersBadge = document.querySelector('.kanban-column.new .badge');
    if (newOrdersBadge) {
        const currentCount = parseInt(newOrdersBadge.textContent) || 0;
        if (currentCount > lastOrderCount && lastOrderCount > 0) {
            // Play notification sound
            try {
                const audio = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2teleN0VV6bS8eKDQwA2pd/x55lLADmk2vXimkoAN6TY9+CZRAA3pNn34JlEAA==');
                audio.play();
            } catch (e) {
                console.log('Sound notification not available');
            }
        }
        lastOrderCount = currentCount;
    }
}

// Initial check
document.addEventListener('DOMContentLoaded', function() {
    checkNewOrders();
});

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

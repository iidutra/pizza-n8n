"""Helpers para atendimento conversacional (público com baixa literacia)."""
import json
import logging
import re
from decimal import Decimal

from django.core.cache import cache

from .order_coverage import parse_llm_item_to_cart

logger = logging.getLogger(__name__)

CONFUSION_THRESHOLD = 2
CONFUSION_TIMEOUT = 3600

CONFIRM_WORDS = {
    'sim', 's', 'isso', 'isso mesmo', 'pode ser', 'pode', 'confirmo', 'confirma',
    'certo', 'ok', 'beleza', 'blz', 'ta certo', 'tá certo', 'correto', 'exato',
    'yes', 'y',
}
DENY_WORDS = {
    'nao', 'não', 'n', 'errado', 'incorreto', 'mudar', 'alterar', 'corrige',
    'corrigir', 'no', 'cancela',
}
HELP_WORDS = {'ajuda', 'help', 'como funciona', 'nao entendi', 'não entendi', 'como pedir'}

GREETING_WORDS = (
    'oi', 'olá', 'ola', 'oie', 'oii', 'bom dia', 'boa tarde', 'boa noite',
    'eae', 'eai', 'e ai', 'e aí', 'opa', 'fala', 'salve', 'tudo bem', 'tudo bom',
    'como vai', 'como você está', 'beleza', 'blz', 'td bem',
)
ORDER_VAGUE_PATTERNS = (
    'quero pedir', 'queria pedir', 'vou pedir', 'fazer pedido', 'fazer um pedido',
    'quero uma pizza', 'queria uma pizza', 'quero pizza', 'queria pizza',
    'pedir uma pizza', 'pedir pizza', 'manda uma pizza', 'vou querer',
)
FLAVOR_KEYWORDS = (
    'calabresa', 'mussarela', 'frango', 'queijo', 'portuguesa', 'bacon', 'baiana',
    'atum', 'strogonoff', 'vegetariana', 'doce', 'banana', 'prestigio', 'prestígio',
    '4 queijos', 'quatro queijos', 'meio a meio', 'meia calabresa', 'promo',
)
FAQ_CARDAPIO = ('cardápio', 'cardapio', 'menu', 'sabores', 'o que tem', 'ver pizza', 'ver o cardapio', 'ver o cardápio')
FAQ_HORARIO = (
    'horário', 'horario', 'que horas', 'hora abre', 'hora fecha', 'abre que',
    'fecha que', 'funciona', 'tá aberto', 'ta aberto', 'esta aberto', 'está aberto',
    'vocês abrem', 'voces abrem', 'vocês fecham', 'voces fecham',
)
FAQ_LOCALIZACAO = (
    'onde fica', 'localização', 'localizacao', 'endereço da pizzaria', 'endereco da pizzaria',
    'como chegar', 'fica onde', 'qual o endereço', 'qual o endereco',
)
FAQ_PAGAMENTO_INFO = (
    'formas de pagamento', 'como paga', 'como posso pagar', 'aceita pix', 'aceita cartão',
    'aceita cartao', 'aceita dinheiro', 'formas de pagar',
)
REPEAT_PATTERNS = (
    'repetir', 'repete', 'de novo', 'denovo', 'mesmo pedido', 'ultimo pedido',
    'último pedido', 'pedido anterior', 'igual da ultima', 'igual da última',
    'o de sempre', 'de sempre', 'igual ontem', 'mesma coisa',
)


def normalize_text(text: str) -> str:
    return (text or '').lower().strip()


def is_confirmation(text: str) -> bool:
    normalized = normalize_text(text)
    return normalized in CONFIRM_WORDS or normalized.startswith('sim ')


def is_denial(text: str) -> bool:
    normalized = normalize_text(text)
    return normalized in DENY_WORDS or normalized.startswith('não ') or normalized.startswith('nao ')


def is_help_request(text: str) -> bool:
    normalized = normalize_text(text)
    return any(word in normalized for word in HELP_WORDS)


def get_conversational_welcome(promo_active: bool = False) -> str:
    """Welcome curto e conversacional — sem menu numérico obrigatório."""
    welcome = (
        "Oi! 🍕 *Pizzaria do Negão*\n\n"
        "Manda seu pedido do *seu jeito*:\n"
        "• por *áudio* 🎤\n"
        "• ou por *texto* (pode escrever do jeito que quiser)\n\n"
        "Exemplo:\n"
        "_\"2 calabresa entrega aponia pix\"_\n\n"
    )
    if promo_active:
        welcome += "🔥 *Promo:* 2 pizzas G por *R$ 55*\n\n"
    welcome += (
        "Também pode falar:\n"
        "• *cardápio* — ver sabores\n"
        "• *promo* — promoção\n"
        "• *ajuda* — como funciona"
    )
    return welcome


def get_help_message() -> str:
    return (
        "É simples! 😊\n\n"
        "1️⃣ Me fala o pedido (áudio ou texto)\n"
        "2️⃣ Eu repito pra você\n"
        "3️⃣ Você responde *SIM* se estiver certo\n"
        "4️⃣ Mando o PIX ou finalizo\n\n"
        "Pode mandar tudo de uma vez:\n"
        "_\"2 calabresa, rua tal 123 aponia, pix\"_"
    )


def _first_name(customer_name: str) -> str:
    name = (customer_name or '').strip().split()[0] if customer_name else ''
    return name.capitalize() if name else ''


def has_greeting(text: str) -> bool:
    normalized = normalize_text(text)
    return any(
        normalized == g or normalized.startswith(f'{g} ') or normalized.startswith(f'{g},')
        or f' {g} ' in f' {normalized} ' or normalized.startswith(g)
        for g in GREETING_WORDS
    )


def wants_to_order_vague(text: str) -> bool:
    normalized = normalize_text(text)
    if any(p in normalized for p in ORDER_VAGUE_PATTERNS):
        return True
    return 'pizza' in normalized and any(w in normalized for w in ('quero', 'queria', 'pedir', 'pedido', 'vou'))


def has_order_details(text: str) -> bool:
    """Sabor, endereço ou pagamento — precisa do LLM."""
    normalized = normalize_text(text)
    if re.search(r'\d{3,5}', normalized):
        return True
    if any(w in normalized for w in FLAVOR_KEYWORDS):
        return True
    if any(w in normalized for w in ('pix', 'dinheiro', 'cartao', 'cartão', 'entrega', 'retirada', 'bairro', 'rua', 'avenida', 'av.')):
        return True
    return False


def is_pure_greeting(text: str) -> bool:
    normalized = normalize_text(text)
    if has_order_details(normalized) or wants_to_order_vague(normalized):
        return False
    if not has_greeting(normalized):
        return False
    return len(normalized.split()) <= 12


def detect_simple_intent(text: str) -> str | None:
    """
    Intenções simples — resposta fixa, sem LLM.
    Retorna: cardapio | horario | localizacao | pagamento_info | saudacao_pedido | saudacao
    """
    normalized = normalize_text(text)
    if not normalized:
        return None

    if any(p in normalized for p in FAQ_CARDAPIO):
        return 'cardapio'
    if any(p in normalized for p in FAQ_HORARIO):
        return 'horario'
    if any(p in normalized for p in FAQ_LOCALIZACAO):
        return 'localizacao'
    if any(p in normalized for p in FAQ_PAGAMENTO_INFO):
        return 'pagamento_info'

    if any(p in normalized for p in REPEAT_PATTERNS):
        return 'repetir_pedido'

    if wants_to_order_vague(normalized) and not has_order_details(normalized):
        return 'saudacao_pedido'
    if is_pure_greeting(normalized):
        return 'saudacao'

    return None


def get_saudacao_pedido_message(customer_name: str = '', promo_active: bool = False) -> str:
    name = _first_name(customer_name)
    hi = f"Oi, {name}!" if name else "Oi!"
    msg = (
        f"{hi} Tudo bem sim 😊\n\n"
        "Que bom que você quer pedir!\n\n"
        "Me fala o sabor (pode ser por *áudio* 🎤):\n"
        "_\"2 calabresa entrega aponia pix\"_\n\n"
    )
    if promo_active:
        msg += "🔥 *Promo:* 2 pizzas G por *R$ 55*\n\n"
    msg += "Ou digite *cardápio* pra ver os sabores"
    return msg


def get_saudacao_message(customer_name: str = '', promo_active: bool = False) -> str:
    name = _first_name(customer_name)
    hi = f"Oi, {name}!" if name else "Oi!"
    msg = (
        f"{hi} Tudo bem? 😊\n\n"
        "Sou o assistente da *Pizzaria do Negão*.\n"
        "Manda seu pedido por *áudio* ou *texto* — do jeito que quiser!\n\n"
        "Exemplo:\n"
        "_\"2 calabresa entrega aponia pix\"_\n\n"
    )
    if promo_active:
        msg += "🔥 *Promo:* 2 pizzas G por *R$ 55*\n\n"
    msg += "Digite *cardápio*, *promo* ou *ajuda*"
    return msg


def get_faq_horario_message(settings) -> str:
    abre = settings.opening_time.strftime('%H:%M')
    fecha = settings.closing_time.strftime('%H:%M')
    return (
        f"🕐 *Horário de funcionamento*\n\n"
        f"Abre: *{abre}*\n"
        f"Fecha: *{fecha}*\n\n"
        f"Entrega: *{settings.min_delivery_time}–{settings.max_delivery_time} min* (depende do bairro)\n\n"
        "Quer pedir? Manda o sabor por áudio ou texto 😊"
    )


def get_faq_localizacao_message(settings) -> str:
    return (
        f"📍 *{settings.business_name}*\n\n"
        "Fazemos *entrega* nos bairros cadastrados.\n"
        "Também pode *retirar* no local.\n\n"
        "Pra pedir, manda: sabor + bairro + forma de pagamento\n"
        "_Ex: \"2 calabresa entrega aponia pix\"_"
    )


def get_faq_pagamento_message(settings) -> str:
    return (
        "💳 *Formas de pagamento*\n\n"
        "• *PIX* (manda o comprovante aqui 📸)\n"
        "• *Dinheiro* (na entrega ou retirada)\n"
        "• *Cartão* crédito ou débito (taxa R$ 2,00 na maquininha)\n\n"
        "Quer pedir? Manda tudo de uma vez:\n"
        "_\"2 calabresa entrega aponia pix\"_"
    )


def get_simple_intent_message(intent: str, settings, customer_name: str = '') -> str | None:
    promo_active = bool(settings.promo_active and settings.promo_text)
    handlers = {
        'saudacao_pedido': lambda: get_saudacao_pedido_message(customer_name, promo_active),
        'saudacao': lambda: get_saudacao_message(customer_name, promo_active),
        'horario': lambda: get_faq_horario_message(settings),
        'localizacao': lambda: get_faq_localizacao_message(settings),
        'pagamento_info': lambda: get_faq_pagamento_message(settings),
    }
    fn = handlers.get(intent)
    return fn() if fn else None


def get_no_previous_order_message() -> str:
    return (
        "Ainda não achei um pedido anterior seu 🤔\n\n"
        "Manda seu pedido do jeito que quiser (áudio ou texto):\n"
        "_\"2 calabresa entrega aponia pix\"_"
    )


def get_audio_ack_message(current_state: str = 'welcome') -> str:
    hints = {
        'awaiting_address': 'Pode falar o endereço: rua, número e bairro.',
        'awaiting_receipt': 'Manda a *foto* do comprovante PIX aqui 📸',
        'awaiting_payment_choice': 'Fala como vai pagar: PIX, dinheiro ou cartão.',
        'awaiting_more_items': 'Fala o sabor ou se é só isso.',
    }
    hint = hints.get(current_state, '')
    msg = 'Recebi seu áudio! Só um instante 🎧'
    if hint:
        msg += f'\n\n_{hint}_'
    return msg


def get_audio_failed_message(current_state: str = 'welcome') -> str:
    return (
        "Não consegui entender o áudio 😅\n\n"
        "Tenta de novo ou escreve assim:\n"
        "_\"2 calabresa entrega aponia\"_\n\n"
        "Ou digite *ajuda*"
    )


def get_simplify_message() -> str:
    return (
        "Vamos simplificar! 😊\n\n"
        "Manda *um áudio* falando:\n"
        "• quantas pizzas\n"
        "• sabor\n"
        "• bairro\n"
        "• como paga\n\n"
        "Eu repito tudo pra você confirmar com *SIM*"
    )


def increment_confusion_count(phone: str) -> int:
    key = f"confusion:{phone}"
    count = cache.get(key) or 0
    count += 1
    cache.set(key, count, CONFUSION_TIMEOUT)
    return count


def reset_confusion_count(phone: str):
    cache.delete(f"confusion:{phone}")


def should_simplify_response(phone: str) -> bool:
    return (cache.get(f"confusion:{phone}") or 0) >= CONFUSION_THRESHOLD


def build_draft_summary(draft: dict) -> str:
    """Formata rascunho do pedido para confirmação."""
    lines = ["*Anotei assim:* 👇", ""]

    for item in draft.get('items', []):
        qty = item.get('quantity', 1)
        if item.get('type') == 'half_half':
            name = item.get('name') or f"½ {item.get('pizza1_name', '')} + ½ {item.get('pizza2_name', '')}"
            lines.append(f"🍕 {qty}x {name}")
        else:
            name = item.get('name', 'Pizza')
            lines.append(f"🍕 {qty}x {name}")

    order_type = draft.get('order_type', 'DELIVERY')
    if order_type == 'PICKUP':
        lines.append("📦 *Retirada* no local")
    elif draft.get('address'):
        lines.append(f"🏠 {draft['address']}")
        if draft.get('neighborhood'):
            lines.append(f"   Bairro: {draft['neighborhood']}")

    payment = draft.get('payment_method')
    payment_labels = {
        'pix': '💳 PIX',
        'cash': '💵 Dinheiro',
        'credit': '💳 Cartão crédito',
        'debit': '💳 Cartão débito',
    }
    if payment and payment != 'unknown':
        lines.append(payment_labels.get(payment, payment))

    subtotal = Decimal(str(draft.get('subtotal', 0)))
    if order_type == 'DELIVERY' and draft.get('delivery_fee') is not None:
        fee = Decimal(str(draft.get('delivery_fee', 0)))
        total = subtotal + fee
        lines.extend(['', f"💰 *Total: R$ {total:.2f}*"])
    elif subtotal:
        lines.extend(['', f"💰 *Total: R$ {subtotal:.2f}*"])

    lines.extend(['', 'Tá certo? Responde *SIM* ou manda o que mudar'])
    return '\n'.join(lines)


def entities_to_draft(entities: dict, address_resolution: dict | None, find_product_fn) -> dict | None:
    """
    Monta rascunho quando LLM extraiu pedido completo o suficiente.
    find_product_fn: callable(name) -> Product|None
    """
    order = entities.get('order') or {}
    items_raw = order.get('items') or []
    if not items_raw:
        return None

    items = []
    subtotal = Decimal('0.00')
    is_promo = order.get('is_promo', False)
    for raw in items_raw:
        cart_item = parse_llm_item_to_cart(raw, find_product_fn, is_promo)
        if not cart_item:
            continue
        qty = cart_item.get('quantity', 1)
        subtotal += Decimal(str(cart_item['price'])) * qty
        items.append(cart_item)

    if not items:
        return None

    delivery_type = entities.get('delivery_type', 'unknown')
    payment = entities.get('payment_method', 'unknown')
    address_data = entities.get('address') or {}

    has_address = bool(address_data.get('address_line') or address_data.get('neighborhood_text'))
    addr_matched = address_resolution and address_resolution.get('status') == 'matched'

    order_type = 'DELIVERY'
    if delivery_type == 'pickup':
        order_type = 'PICKUP'
    elif delivery_type == 'delivery' or (has_address and addr_matched):
        order_type = 'DELIVERY'

    complete = (
        (order_type == 'PICKUP' or (has_address and addr_matched))
        and payment not in (None, '', 'unknown')
    )
    if not complete:
        return None

    full_address = f"{address_data.get('address_line', '')} {address_data.get('number', '')}".strip()
    if address_data.get('complement'):
        full_address += f", {address_data.get('complement')}"

    draft = {
        'items': items,
        'order_type': order_type,
        'payment_method': payment,
        'subtotal': float(subtotal),
        'delivery_fee': 0,
        'neighborhood': None,
        'address': full_address or None,
        'change_for': entities.get('change_for'),
        'is_promo': order.get('is_promo', False),
        'raw_entities': entities,
    }

    if order_type == 'DELIVERY' and addr_matched:
        draft['neighborhood'] = address_resolution.get('matched_neighborhood')
        draft['delivery_fee'] = float(address_resolution.get('delivery_fee') or 0)

    return draft


def save_draft_state(set_state_fn, phone: str, draft: dict):
    """Salva rascunho no estado da conversa."""
    set_state_fn(phone, 'awaiting_draft_confirmation', {'draft': draft, 'failed_count': 0})


def get_draft_from_state(state: dict) -> dict | None:
    return (state.get('data') or {}).get('draft')

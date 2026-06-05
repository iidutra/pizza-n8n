"""Cobertura ampliada: pedido parcial, repetir último pedido, parsing de campos."""
import re
from decimal import Decimal

from .models import Customer, DeliveryFee, Order, Product

REPEAT_PATTERNS = (
    'repetir', 'repete', 'de novo', 'denovo', 'mesmo pedido', 'ultimo pedido',
    'último pedido', 'pedido anterior', 'igual da ultima', 'igual da última',
    'o de sempre', 'de sempre', 'igual ontem', 'mesma coisa', 'igual da outra vez',
)

PAYMENT_MAP = {
    'pix': 'pix', 'dinheiro': 'cash', 'cash': 'cash', 'cartao': 'credit',
    'cartão': 'credit', 'credito': 'credit', 'crédito': 'credit',
    'debito': 'debit', 'débito': 'debit', 'cartao debito': 'debit',
}


def is_repeat_order_request(text: str) -> bool:
    normalized = (text or '').lower().strip()
    return any(p in normalized for p in REPEAT_PATTERNS)


def _payment_from_order(order: Order) -> str:
    mapping = {'PIX': 'pix', 'CASH': 'cash', 'CREDIT': 'credit', 'DEBIT': 'debit'}
    return mapping.get(order.payment_method or '', 'unknown')


def get_last_order_for_customer(phone: str) -> Order | None:
    customer = Customer.objects.filter(phone=phone).first()
    if not customer:
        return None
    return (
        Order.objects.filter(customer=customer)
        .exclude(status='CANCELLED')
        .prefetch_related('items__product')
        .order_by('-created_at')
        .first()
    )


def order_to_draft(order: Order) -> dict | None:
    items = []
    subtotal = Decimal('0.00')
    for oi in order.items.all():
        items.append({
            'name': oi.product.name,
            'quantity': oi.quantity,
            'product_id': oi.product_id,
            'price': float(oi.unit_price),
        })
        subtotal += Decimal(str(oi.unit_price)) * oi.quantity
    if not items:
        return None
    return {
        'items': items,
        'order_type': order.order_type,
        'payment_method': _payment_from_order(order),
        'subtotal': float(subtotal),
        'delivery_fee': float(order.delivery_fee or 0),
        'neighborhood': order.neighborhood or None,
        'address': order.delivery_address or None,
        'is_promo': False,
        'from_repeat': True,
    }


def build_repeat_order_message(draft: dict) -> str:
    from .conversational_helpers import build_draft_summary
    summary = build_draft_summary(draft)
    return summary.replace(
        'Tá certo? Responde *SIM* ou manda o que mudar',
        'Quer *repetir* esse pedido? Responde *SIM* ou manda o que mudar',
    )


def parse_llm_item_to_cart(raw: dict, find_product_fn, is_promo: bool = False) -> dict | None:
    """Converte item do LLM em item do carrinho (simples ou meio a meio)."""
    if raw.get('is_half_half') or raw.get('half_flavors'):
        flavors = raw.get('half_flavors') or []
        if len(flavors) < 2 and raw.get('name'):
            return None
        if len(flavors) >= 2:
            p1 = find_product_fn(flavors[0])
            p2 = find_product_fn(flavors[1])
            if p1 and p2:
                price = max(float(p1.price), float(p2.price))
                if is_promo:
                    price = 27.50
                qty = int(raw.get('quantity') or 1)
                label = f"½ {p1.name} + ½ {p2.name}"
                return {
                    'type': 'half_half',
                    'pizza1_id': p1.id,
                    'pizza2_id': p2.id,
                    'pizza1_name': p1.name,
                    'pizza2_name': p2.name,
                    'product_id': p1.id,
                    'name': label,
                    'price': price,
                    'quantity': qty,
                }
        return None

    name = (raw.get('name') or '').strip()
    if not name:
        return None
    product = find_product_fn(name)
    if not product:
        return None
    qty = int(raw.get('quantity') or 1)
    price = 27.50 if is_promo else float(product.price)
    return {
        'name': product.name,
        'quantity': qty,
        'product_id': product.id,
        'price': price,
    }


def entities_to_partial_draft(entities: dict, address_resolution: dict | None, find_product_fn) -> dict | None:
    """Monta rascunho parcial com o que o LLM extraiu (pedido incompleto OK)."""
    order = entities.get('order') or {}
    items_raw = order.get('items') or []
    if not items_raw:
        return None

    is_promo = order.get('is_promo', False)
    items = []
    subtotal = Decimal('0.00')
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
    payment = (entities.get('payment_method') or 'unknown').lower()
    address_data = entities.get('address') or {}

    order_type = 'DELIVERY'
    if delivery_type == 'pickup':
        order_type = 'PICKUP'
    elif delivery_type == 'unknown' and not (address_data.get('address_line') or address_data.get('neighborhood_text')):
        order_type = 'unknown'

    full_address = f"{address_data.get('address_line', '')} {address_data.get('number', '')}".strip()
    if address_data.get('complement'):
        full_address += f", {address_data.get('complement')}"

    neighborhood = None
    delivery_fee = 0.0
    if address_resolution and address_resolution.get('status') == 'matched':
        neighborhood = address_resolution.get('matched_neighborhood')
        delivery_fee = float(address_resolution.get('delivery_fee') or 0)
    elif address_data.get('neighborhood_text'):
        neighborhood = address_data.get('neighborhood_text')

    return {
        'items': items,
        'order_type': order_type,
        'payment_method': payment,
        'subtotal': float(subtotal),
        'delivery_fee': delivery_fee,
        'neighborhood': neighborhood,
        'address': full_address or None,
        'is_promo': is_promo,
    }


def get_missing_fields(partial: dict) -> list[str]:
    missing = []
    order_type = partial.get('order_type', 'unknown')

    if order_type == 'unknown':
        missing.append('order_type')

    if order_type == 'DELIVERY':
        has_addr = partial.get('address') or partial.get('neighborhood')
        if not has_addr:
            missing.append('address')
        elif partial.get('neighborhood') and not partial.get('delivery_fee'):
            fee = DeliveryFee.objects.filter(
                neighborhood__iexact=partial['neighborhood'], active=True
            ).first()
            if not fee:
                missing.append('address')

    payment = partial.get('payment_method')
    if not payment or payment == 'unknown':
        missing.append('payment')

    return missing


FIELD_QUESTIONS = {
    'order_type': (
        "É *entrega* 🛵 ou *retirada* no local 📦?\n\n"
        "Responde: *entrega* ou *retirada*"
    ),
    'address': (
        "Qual o endereço? 🏠\n\n"
        "Pode mandar por *áudio* ou escrever:\n"
        "_\"rua tal 123 bairro aponia\"_"
    ),
    'payment': (
        "Como vai pagar? 💳\n\n"
        "Responde: *PIX*, *dinheiro* ou *cartão*"
    ),
}


def get_question_for_field(field: str) -> str:
    return FIELD_QUESTIONS.get(field, "Pode repetir?")


def build_partial_progress_message(partial: dict, waiting_field: str) -> str:
    lines = ["*Anotei até aqui:* 👇", ""]

    for item in partial.get('items', []):
        qty = item.get('quantity', 1)
        name = item.get('name', 'Pizza')
        if item.get('type') == 'half_half' and not name.startswith('½'):
            name = f"½ {item.get('pizza1_name', '')} + ½ {item.get('pizza2_name', '')}"
        lines.append(f"🍕 {qty}x {name}")

    if partial.get('order_type') == 'PICKUP':
        lines.append("📦 Retirada no local")
    elif partial.get('address'):
        lines.append(f"🏠 {partial['address']}")
        if partial.get('neighborhood'):
            lines.append(f"   Bairro: {partial['neighborhood']}")

    payment = partial.get('payment_method')
    if payment and payment != 'unknown':
        labels = {'pix': '💳 PIX', 'cash': '💵 Dinheiro', 'credit': '💳 Cartão', 'debit': '💳 Cartão débito'}
        lines.append(labels.get(payment, payment))

    lines.extend(['', 'Só falta uma coisa:', '', get_question_for_field(waiting_field)])
    return '\n'.join(lines)


def parse_payment_from_text(text: str) -> str | None:
    normalized = (text or '').lower().strip()
    if normalized in ('pix', 'dinheiro', 'cartao', 'cartão', 'credito', 'crédito', 'debito', 'débito', 'cartão'):
        return PAYMENT_MAP.get(normalized, 'credit' if 'cart' in normalized else None)
    if 'pix' in normalized:
        return 'pix'
    if 'dinheiro' in normalized or normalized == 'cash':
        return 'cash'
    if 'cart' in normalized or 'cartão' in normalized or 'cartao' in normalized:
        return 'credit'
    for key, val in PAYMENT_MAP.items():
        if key in normalized:
            return val
    return None


def parse_order_type_from_text(text: str) -> str | None:
    normalized = (text or '').lower().strip()
    if normalized in ('retirada', 'retirar', 'buscar', 'pickup'):
        return 'PICKUP'
    if normalized in ('entrega', 'delivery', 'entregar'):
        return 'DELIVERY'
    return None


def match_neighborhood_in_text(text: str) -> tuple[str | None, float]:
    """Retorna (bairro, taxa) se encontrar match."""
    all_fees = list(DeliveryFee.objects.filter(active=True))
    if not all_fees:
        return None, 0.0

    normalized = (text or '').lower()
    words = [w for w in re.sub(r'[^\w\s]', ' ', normalized).split() if len(w) >= 3]

    best_match = None
    best_score = 0
    for fee in all_fees:
        bairro_lower = fee.neighborhood.lower()
        if bairro_lower in normalized:
            return fee.neighborhood, float(fee.fee)
        for word in words:
            if word in bairro_lower or bairro_lower in word:
                score = 85
            elif len(word) >= 3 and word[:3] == bairro_lower[:3]:
                score = 65
            else:
                common = sum(1 for c in word if c in bairro_lower)
                score = int((common / max(len(word), len(bairro_lower))) * 100)
            if score > best_score and score >= 55:
                best_score = score
                best_match = fee

    if best_match:
        return best_match.neighborhood, float(best_match.fee)
    return None, 0.0


def fill_partial_field(partial: dict, field: str, text: str, find_product_fn) -> dict | None:
    """Preenche um campo do rascunho parcial. Retorna None se não entendeu."""
    updated = {**partial}

    if field == 'payment':
        payment = parse_payment_from_text(text)
        if not payment:
            return None
        updated['payment_method'] = payment
        return updated

    if field == 'order_type':
        order_type = parse_order_type_from_text(text)
        if not order_type:
            return None
        updated['order_type'] = order_type
        if order_type == 'PICKUP':
            updated['address'] = None
            updated['neighborhood'] = None
            updated['delivery_fee'] = 0
        return updated

    if field == 'address':
        updated['address'] = text.strip()
        neighborhood, fee = match_neighborhood_in_text(text)
        if neighborhood:
            updated['neighborhood'] = neighborhood
            updated['delivery_fee'] = fee
        return updated

    if field == 'items':
        product = find_product_fn(text)
        if not product:
            return None
        qty = 1
        m = re.search(r'(\d+)\s', text)
        if m:
            qty = int(m.group(1))
        price = float(product.price)
        updated['items'] = [{
            'name': product.name,
            'quantity': qty,
            'product_id': product.id,
            'price': price,
        }]
        updated['subtotal'] = price * qty
        return updated

    return None


def partial_to_complete_draft(partial: dict) -> dict | None:
    """Converte rascunho parcial em completo se todos os campos OK."""
    if get_missing_fields(partial):
        return None
    return partial

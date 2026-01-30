import json
import logging
import re
from decimal import Decimal

from django.core.cache import cache
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.core.files.base import ContentFile

from fuzzywuzzy import fuzz, process
import requests
import base64

from .models import Customer, Product, DeliveryFee, Order, OrderItem, BusinessSettings
from .waha_service import send_whatsapp_message, send_whatsapp_image, WAHA_URL, WAHA_SESSION

logger = logging.getLogger(__name__)

CONVERSATION_TIMEOUT = 3600  # 1 hora
MESSAGE_DEDUP_TIMEOUT = 300  # 5 minutos para deduplicação


def get_help_text() -> str:
    """Retorna texto de ajuda com comandos disponíveis."""
    return "\n\n_Comandos: 'voltar' (etapa anterior) | 'cancelar' (desistir do pedido)_"


def format_order_summary(items: list, delivery_fee: Decimal = None, order_type: str = 'DELIVERY', is_promo: bool = False) -> str:
    """Formata resumo do pedido."""
    summary = "*RESUMO DO PEDIDO*\n"
    subtotal = Decimal('0.00')

    if is_promo:
        summary += "🔥 *PROMOÇÃO 2 PIZZAS*\n"

    for item_data in items:
        try:
            item_type = item_data.get("type", "single")
            qty = item_data.get("quantity", 1)
            obs = item_data.get("observation", "")

            if item_type == "half_half":
                # Pizza meio a meio
                item_price = Decimal(str(item_data.get("price", 0)))
                pizza1_name = item_data.get("pizza1_name", "")
                pizza2_name = item_data.get("pizza2_name", "")
                item_name = f"½ {pizza1_name} + ½ {pizza2_name}"
            else:
                # Pizza normal
                product = Product.objects.get(id=item_data["product_id"])
                # Usa preço promocional se existir
                if "promo_price" in item_data:
                    item_price = Decimal(str(item_data["promo_price"]))
                elif "price" in item_data:
                    item_price = Decimal(str(item_data["price"]))
                else:
                    item_price = product.price
                item_name = product.name

            item_total = item_price * qty
            subtotal += item_total
            summary += f"- {qty}x {item_name}: R$ {item_total:.2f}\n"

            if obs:
                summary += f"  📝 _{obs}_\n"

        except Product.DoesNotExist:
            continue

    summary += f"\nSubtotal: R$ {subtotal:.2f}"

    if order_type == 'DELIVERY' and delivery_fee:
        summary += f"\nTaxa de entrega: R$ {delivery_fee:.2f}"
        summary += f"\n*TOTAL: R$ {(subtotal + delivery_fee):.2f}*"
    else:
        summary += f"\n*TOTAL: R$ {subtotal:.2f}*"

    return summary


def is_message_duplicate(message_id: str) -> bool:
    """Verifica se a mensagem já foi processada (evita duplicação)."""
    if not message_id:
        return False

    key = f"msg_processed:{message_id}"

    # Usa add() que é atômico - retorna True apenas se a chave NÃO existia
    # Se a chave já existe, add() retorna False
    was_added = cache.add(key, "1", MESSAGE_DEDUP_TIMEOUT)

    # Se conseguiu adicionar, é a primeira vez (não é duplicata)
    # Se não conseguiu adicionar, já existia (é duplicata)
    return not was_added


def get_conversation_state(phone: str) -> dict:
    """Recupera estado da conversa do Redis."""
    key = f"conversation:{phone}"
    state = cache.get(key)
    if state:
        return json.loads(state)
    return {"state": "welcome", "data": {}}


def set_conversation_state(phone: str, state: str, data: dict = None, save_history: bool = True):
    """Salva estado da conversa no Redis."""
    key = f"conversation:{phone}"
    current = get_conversation_state(phone)

    # Salva estado anterior no histórico para permitir "voltar"
    if save_history and current["state"] != state and current["state"] != "welcome":
        history = current.get("history", [])
        history.append({
            "state": current["state"],
            "data": current["data"].copy()
        })
        # Mantém apenas os últimos 5 estados
        current["history"] = history[-5:]

    current["state"] = state
    if data:
        current["data"].update(data)
    cache.set(key, json.dumps(current), CONVERSATION_TIMEOUT)


def clear_conversation_state(phone: str):
    """Limpa estado da conversa."""
    key = f"conversation:{phone}"
    cache.delete(key)


def go_back_state(phone: str) -> tuple:
    """Volta para o estado anterior. Retorna (sucesso, mensagem)."""
    state = get_conversation_state(phone)
    history = state.get("history", [])

    if not history:
        return False, "Voce esta no inicio. Nao ha como voltar." + get_help_text()

    # Recupera o último estado do histórico
    previous = history.pop()

    # Atualiza o estado atual
    key = f"conversation:{phone}"
    new_state = {
        "state": previous["state"],
        "data": previous["data"],
        "history": history
    }
    cache.set(key, json.dumps(new_state), CONVERSATION_TIMEOUT)

    # Retorna mensagem apropriada para o estado
    state_messages = {
        "welcome": "Certo! Qual e o seu pedido para hoje?",
        "awaiting_promo_pizza_1": "Promoção: 2 Pizzas por R$ 55! Qual o primeiro sabor?",
        "awaiting_promo_pizza_2": "Qual o segundo sabor da promoção?",
        "awaiting_promo_order_type": "Vai ser entrega ou retirada?\n1. Entrega\n2. Retirada",
        "awaiting_half_half_first": "Pizza meio a meio! Qual o primeiro sabor?",
        "awaiting_half_half_second": "Qual o segundo sabor da meio a meio?",
        "awaiting_observation": "Alguma observação? (tirar cebola, sem tomate, etc)\n\nDigite a observação ou 'não' se não tiver",
        "awaiting_pickup_items": "Certo, voce vai retirar no local! Qual vai ser o pedido?",
        "awaiting_more_items": "Deseja adicionar mais alguma pizza?\n1. Sim, quero mais pizza\n2. Nao, so isso",
        "awaiting_another_item": "Qual pizza voce quer adicionar?",
        "awaiting_more_items_pickup": "Deseja adicionar mais alguma pizza?\n1. Sim, quero mais pizza\n2. Nao, so isso",
        "awaiting_drink": get_drinks_menu(),
        "awaiting_drink_pickup": get_drinks_menu(),
        "awaiting_address": "Confirme o endereco completo (rua, numero e bairro), por gentileza.",
        "confirming_delivery": "Confirma o pedido para ENTREGA?\n1. Sim, confirmar\n2. Nao, cancelar",
        "confirming_pickup": "Confirma o pedido para RETIRADA?\n1. Sim, confirmar\n2. Nao, cancelar",
        "awaiting_receipt": "Aguardando comprovante de pagamento (foto).\nOu digite 'pagar na entrega' para pagar ao receber.",
        "awaiting_payment_method": "Como vai ser o pagamento na entrega?\n1. Dinheiro\n2. Cartão (taxa de R$ 2,00)",
        "awaiting_change": "Vai precisar de troco? Se sim, pra quanto?",
        "awaiting_card_type": "Cartão: vai ser crédito ou débito?\n1. Crédito\n2. Débito",
        "awaiting_half_or_full": "Como você quer?\n1. Meio a meio\n2. Duas pizzas inteiras",
        "awaiting_promo_half_or_full": "Promoção - como você quer?\n1. Meio a meio\n2. Duas pizzas inteiras",
        "awaiting_promo_second_after_half": "Promoção meio a meio! Qual o segundo sabor?",
    }

    return True, state_messages.get(previous["state"], "Qual e o seu pedido para hoje?") + get_help_text()


def handle_cancel(phone: str) -> str:
    """Cancela a conversa atual e volta ao início."""
    state = get_conversation_state(phone)
    order_id = state.get("data", {}).get("order_id")

    # Se tem um pedido em andamento, cancela
    if order_id:
        try:
            order = Order.objects.get(id=order_id)
            if order.status in ['AWAITING_PAYMENT', 'PREPARING']:
                order.status = 'CANCELLED'
                order.save()
        except Order.DoesNotExist:
            pass

    clear_conversation_state(phone)
    return "Sem problemas! Cancelei aqui. 👍\nQuando quiser pedir é só mandar um oi! 😊"


def is_back_command(message: str) -> bool:
    """Verifica se é um comando de voltar."""
    back_words = ['voltar', 'volta', 'anterior', 'atras', 'atrás', 'back']
    return message.lower().strip() in back_words


def is_cancel_command(message: str) -> bool:
    """Verifica se é um comando de cancelar/sair."""
    cancel_words = ['cancelar', 'cancela', 'sair', 'desistir', 'parar', 'exit', 'quit', 'tchau', 'bye']
    return message.lower().strip() in cancel_words


def get_or_create_customer(phone: str, name: str = None) -> Customer:
    """Busca ou cria cliente pelo telefone."""
    customer, created = Customer.objects.get_or_create(
        phone=phone,
        defaults={"name": name or "Cliente"}
    )
    if name and customer.name == "Cliente":
        customer.name = name
        customer.save()
    return customer


def find_product_fuzzy(text: str) -> Product:
    """Encontra produto por correspondencia fuzzy."""
    original_text = text
    text = text.lower().strip()
    logger.info(f"DEBUG find_product_fuzzy: original={repr(original_text)}, after_strip={repr(text)}, isdigit={text.isdigit()}")

    # Se é um número, busca direto pelo índice do cardápio (só pizzas salgadas)
    if text.isdigit():
        idx = int(text)
        pizzas = list(Product.objects.filter(category='PIZZA', active=True).order_by('name'))
        logger.info(f"DEBUG find_product_fuzzy: numero={idx}, total_pizzas={len(pizzas)}, pizzas={[p.name for p in pizzas[:5]]}")
        if 1 <= idx <= len(pizzas):
            return pizzas[idx - 1]
        logger.warning(f"DEBUG: Numero {idx} fora do range 1-{len(pizzas)}")
        return None

    # Ignora palavras genéricas que não são sabores
    ignore_words = ['pizza', 'grande', 'media', 'média', 'pequena', 'quero', 'uma', 'duas', 'favor', 'por']
    clean_text = text
    for word in ignore_words:
        clean_text = clean_text.replace(word, '').strip()

    # Se sobrou só espaço ou nada, não encontrou
    if not clean_text or len(clean_text) < 3:
        return None

    # Mapeamento de nomes para pizzas (busca por palavras-chave)
    pizza_keywords = [
        ("mussarela", "mussarela"), ("mucarela", "mussarela"), ("muzarela", "mussarela"),
        ("calabresa", "calabresa"),
        ("frango catupiry", "frango com catupiry"), ("frango com catupiry", "frango com catupiry"),
        ("frango cheddar", "frango com cheddar"), ("frango com cheddar", "frango com cheddar"),
        ("frango milho", "frango com milho"), ("frango com milho", "frango com milho"),
        ("calabresa catupiry", "calabresa com catupiry"), ("calabresa com catupiry", "calabresa com catupiry"),
        ("atum", "atum"),
        ("palmito", "palmito"),
        ("francesa", "francesa"),
        ("baiana", "baiana"),
        ("mexicana", "mexicana"),
        ("bacon", "bacon"),
        ("bauru", "bauru"),
        ("portuguesa", "portuguesa"),
        ("4 queijos", "4 queijos"), ("quatro queijos", "4 queijos"), ("queijos", "4 queijos"),
        ("marguerita", "marguerita"), ("margerita", "marguerita"),
        ("pepperoni", "pepperoni"), ("peperoni", "pepperoni"),
        # Pizzas doces
        ("brigadeiro", "brigadeiro"),
        ("prestigio", "prestígio"), ("prestígio", "prestígio"),
        ("banana", "banana"),
    ]

    for keyword, name in pizza_keywords:
        if keyword in clean_text:
            # Busca em pizzas salgadas e doces
            product = Product.objects.filter(
                name__icontains=name,
                category__in=['PIZZA', 'PIZZA_DOCE'],
                active=True
            ).first()
            if product:
                return product

    # Busca fuzzy em todas as pizzas (salgadas e doces)
    products = Product.objects.filter(active=True, category__in=['PIZZA', 'PIZZA_DOCE'])
    product_names = [(p.name.lower(), p) for p in products]

    if product_names:
        best_match = process.extractOne(
            clean_text,
            [name for name, _ in product_names],
            scorer=fuzz.partial_ratio
        )
        if best_match and best_match[1] >= 70:
            for name, product in product_names:
                if name == best_match[0]:
                    return product

    return None


def find_drink_by_option(option: str) -> Product:
    """Encontra bebida pela opcao selecionada."""
    drinks = list(Product.objects.filter(category='BEBIDA', active=True)[:4])

    option = option.strip()

    # Por número
    if option.isdigit():
        idx = int(option) - 1
        if 0 <= idx < len(drinks):
            return drinks[idx]

    # Por nome
    option_lower = option.lower()
    for drink in drinks:
        if any(word in drink.name.lower() for word in option_lower.split()):
            return drink

    return None


def find_neighborhood_fee(neighborhood: str) -> DeliveryFee:
    """Encontra taxa de entrega pelo bairro."""
    neighborhood = neighborhood.lower().strip()

    exact = DeliveryFee.objects.filter(
        neighborhood__iexact=neighborhood,
        active=True
    ).first()
    if exact:
        return exact

    fees = DeliveryFee.objects.filter(active=True)
    fee_names = [(f.neighborhood.lower(), f) for f in fees]

    if fee_names:
        best_match = process.extractOne(
            neighborhood,
            [name for name, _ in fee_names],
            scorer=fuzz.partial_ratio
        )
        if best_match and best_match[1] >= 70:
            for name, fee in fee_names:
                if name == best_match[0]:
                    return fee

    return None


def get_drinks_menu() -> str:
    """Retorna menu de bebidas formatado."""
    drinks = Product.objects.filter(category='BEBIDA', active=True)[:4]
    menu = "E pra beber, vai querer alguma coisa? 🥤\n\n"

    for i, drink in enumerate(drinks, 1):
        menu += f"{i}️⃣ {drink.name} - R$ {drink.price:.2f}\n"

    menu += f"{len(drinks) + 1}️⃣ Não, só a pizza mesmo\n\n"
    menu += "_'voltar' | 'sair'_"
    return menu


def is_half_half_request(text: str) -> bool:
    """Verifica se é um pedido de pizza meio a meio."""
    text_lower = text.lower().strip()
    half_patterns = ['meio', 'metade', '1/2', 'meia', 'meio a meio', 'metade metade']

    # Padrão "1 sabor e sabor2" também é meio a meio
    if re.match(r'^1\s+\w+.*\s+e\s+\w+', text_lower):
        return True

    # Padrão "sabor com metade de sabor" ou "sabor e metade sabor"
    if re.search(r'\w+\s+(com\s+metade|e\s+metade|metade\s+de|com\s+meia|e\s+meia)\s+\w+', text_lower):
        return True

    return any(pattern in text_lower for pattern in half_patterns)


def parse_half_half(text: str) -> tuple:
    """Tenta extrair os dois sabores de um pedido meio a meio."""
    text_lower = text.lower().strip()

    # Padrão numérico: "1 e 2", "1,2", "1 e a pizza 2", "1 com 2"
    # Retorna os números como string para serem convertidos em produtos depois
    match = re.match(r'^(\d+)\s*[,e]\s*(\d+)$', text_lower)
    if match:
        return f"#{match.group(1)}", f"#{match.group(2)}"

    match = re.match(r'^(\d+)\s+e\s+(?:a\s+)?(?:pizza\s+)?(\d+)$', text_lower)
    if match:
        return f"#{match.group(1)}", f"#{match.group(2)}"

    match = re.match(r'^(\d+)\s+com\s+(\d+)$', text_lower)
    if match:
        return f"#{match.group(1)}", f"#{match.group(2)}"

    # Padrão: "calabresa com metade de baiana" ou "calabresa com metade baiana"
    match = re.match(r'^(.+?)\s+(?:com\s+metade\s+(?:de\s+)?|e\s+metade\s+(?:de\s+)?|metade\s+)(.+)$', text_lower)
    if match:
        sabor1 = match.group(1).strip()
        sabor2 = match.group(2).strip()
        # Limpa palavras extras
        sabor1 = re.sub(r'^(meia|meio|metade)\s+', '', sabor1)
        sabor2 = re.sub(r'^(meia|meio|metade|de)\s+', '', sabor2)
        if sabor1 and sabor2:
            return sabor1, sabor2

    # Padrão: "1 calabresa e bacon" -> meio a meio
    match = re.match(r'^1\s+(.+?)\s+e\s+(.+)$', text_lower)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # Padrão: "meio calabresa meio baiana" ou "metade X metade Y"
    match = re.match(r'^(?:meio|meia|metade)\s+(.+?)\s+(?:meio|meia|metade)\s+(.+)$', text_lower)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # Padrão: "calabresa e baiana" (simples, sem meio/metade explícito mas com "e")
    # Só usa se tiver exatamente 2 sabores separados por "e"
    if ' e ' in text_lower and 'meio' not in text_lower and 'metade' not in text_lower:
        parts = text_lower.split(' e ')
        if len(parts) == 2:
            sabor1 = parts[0].strip()
            sabor2 = parts[1].strip()
            # Verifica se ambos parecem sabores válidos (não são números ou palavras curtas)
            if len(sabor1) > 2 and len(sabor2) > 2:
                return sabor1, sabor2

    # Padrões com separadores
    separators = [' com ', '/']
    for sep in separators:
        if sep in text_lower:
            parts = text_lower.split(sep)
            if len(parts) >= 2:
                sabor1 = parts[0].replace('meio', '').replace('metade', '').replace('1/2', '').strip()
                sabor2 = parts[-1].replace('meio', '').replace('metade', '').replace('1/2', '').replace('de ', '').strip()
                # Remove números no início
                sabor1 = re.sub(r'^\d+\s*', '', sabor1)
                sabor2 = re.sub(r'^\d+\s*', '', sabor2)
                if sabor1 and sabor2:
                    return sabor1, sabor2

    return None, None


def resolve_half_half_by_number(sabor: str) -> Product:
    """Se o sabor começa com #, é um número do cardápio. Converte para produto."""
    if sabor.startswith('#'):
        idx = int(sabor[1:])
        pizzas = list(Product.objects.filter(category='PIZZA', active=True).order_by('name'))
        if 1 <= idx <= len(pizzas):
            return pizzas[idx - 1]
        return None
    return find_product_fuzzy(sabor)


def parse_two_numbers(text: str) -> tuple:
    """Extrai dois números de seleção do cardápio. Ex: '1 e 2', '1,2', '1 e a pizza 2'"""
    text_lower = text.lower().strip()

    # Padrão: "1 e 2", "1,2", "1 e a pizza 2", "1 com 2"
    patterns = [
        r'^(\d+)\s*[,]\s*(\d+)$',  # 1,2
        r'^(\d+)\s+e\s+(\d+)$',  # 1 e 2
        r'^(\d+)\s+e\s+(?:a\s+)?(?:pizza\s+)?(\d+)$',  # 1 e a pizza 2
        r'^(\d+)\s+com\s+(\d+)$',  # 1 com 2
    ]

    for pattern in patterns:
        match = re.match(pattern, text_lower)
        if match:
            return int(match.group(1)), int(match.group(2))

    return None


def handle_half_or_full(phone: str, message: str) -> str:
    """Trata escolha entre meio a meio ou duas pizzas inteiras."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    pizza1_id = state["data"].get("pizza1_id")
    pizza2_id = state["data"].get("pizza2_id")
    pizza1_name = state["data"].get("pizza1_name")
    pizza2_name = state["data"].get("pizza2_name")

    try:
        pizza1 = Product.objects.get(id=pizza1_id)
        pizza2 = Product.objects.get(id=pizza2_id)
    except Product.DoesNotExist:
        clear_conversation_state(phone)
        return "Ops, algo deu errado 😅 Vamos recomeçar!"

    # Meio a meio
    if message_lower in ['1', 'meio', 'metade', 'meio a meio', 'meia']:
        preco = max(pizza1.price, pizza2.price)
        set_conversation_state(phone, "awaiting_observation", {
            "order_type": "DELIVERY",
            "current_item": {
                "type": "half_half",
                "pizza1_id": pizza1.id,
                "pizza2_id": pizza2.id,
                "pizza1_name": pizza1.name,
                "pizza2_name": pizza2.name,
                "price": float(preco)
            },
            "items": []
        })
        return (
            f"Boa! 🍕 *Meio a Meio:*\n"
            f"½ {pizza1.name} + ½ {pizza2.name}\n"
            f"💰 R$ {preco:.2f}\n\n"
            f"Alguma observação? (tirar cebola, sem tomate, etc)\n\n"
            f"_Digite a observação ou 'não' se não tiver_"
        )

    # Duas pizzas inteiras
    if message_lower in ['2', 'duas', 'inteira', 'inteiras', 'separadas', 'separado']:
        items = [
            {"type": "single", "product_id": pizza1.id, "quantity": 1, "price": float(pizza1.price)},
            {"type": "single", "product_id": pizza2.id, "quantity": 1, "price": float(pizza2.price)}
        ]
        total = pizza1.price + pizza2.price
        set_conversation_state(phone, "awaiting_more_items", {
            "order_type": "DELIVERY",
            "items": items
        })
        return (
            f"Anotado! ✅\n\n"
            f"• 1x *{pizza1.name}* - R$ {pizza1.price:.2f}\n"
            f"• 1x *{pizza2.name}* - R$ {pizza2.price:.2f}\n"
            f"💰 Subtotal: R$ {total:.2f}\n\n"
            f"Quer mais alguma pizza?\n"
            f"1️⃣ Quero mais\n"
            f"2️⃣ Só isso"
        )

    return "Não entendi 😅 Digite 1 para meio a meio ou 2 para duas pizzas inteiras.\n\n_'voltar' | 'cancelar'_"


def parse_multiple_pizzas(text: str) -> list:
    """
    Tenta extrair múltiplas pizzas de um pedido.
    Ex: "2 portuguesa e 4 queijo" -> [('portuguesa', 1), ('4 queijos', 1)]
    Ex: "1 calabresa e bacon" -> meio a meio
    """
    text_lower = text.lower().strip()
    pizzas = []

    # Padrão: "2 portuguesa e 4 queijo" (duas pizzas diferentes)
    # Ou: "1 calabresa, 1 portuguesa"
    patterns = [
        r'(\d+)\s+([a-záéíóúàâêôãõç\s]+?)(?:\s+e\s+|\s*,\s*)(\d+)\s+([a-záéíóúàâêôãõç\s]+)',  # "2 portuguesa e 4 queijo"
    ]

    for pattern in patterns:
        match = re.match(pattern, text_lower)
        if match:
            qty1 = int(match.group(1))
            sabor1 = match.group(2).strip()
            qty2 = int(match.group(3))
            sabor2 = match.group(4).strip()

            product1 = find_product_fuzzy(sabor1)
            product2 = find_product_fuzzy(sabor2)

            if product1 and product2:
                return [
                    {'product': product1, 'quantity': qty1},
                    {'product': product2, 'quantity': qty2}
                ]

    return None


def handle_welcome(phone: str, message: str, msg_type: str) -> str:
    """Trata estado inicial."""
    message_lower = message.lower().strip()
    settings_obj = BusinessSettings.get_settings()
    promo_active = settings_obj.promo_active and settings_obj.promo_text

    # Verifica se quer promoção
    if message_lower == '1' and promo_active:
        return handle_promo_order(phone)

    if any(word in message_lower for word in ['promo', 'promocao', 'promoção', 'oferta', '2 pizza', 'duas pizza']):
        if promo_active:
            return handle_promo_order(phone)
        return handle_promo_request(phone)

    # Opção 2 (com promo) ou 1 (sem promo) - ver cardápio
    if (message_lower == '2' and promo_active) or (message_lower == '1' and not promo_active):
        return handle_menu_request(phone)

    if any(word in message_lower for word in ['cardapio', 'cardápio', 'menu', 'catalogo', 'ver', 'quero ver', 'manda']):
        return handle_menu_request(phone)

    # Opção 3 (com promo) ou 2 (sem promo) - já sabe o que quer
    if (message_lower == '3' and promo_active) or (message_lower == '2' and not promo_active):
        return "Beleza! Me fala o sabor da pizza que você quer 🍕\n\n_Dica: pode pedir meio a meio! Ex: 'meio calabresa meio mussarela'_"

    if any(word in message_lower for word in ['ja sei', 'já sei', 'sei o que', 'quero pedir']):
        return "Beleza! Me fala o sabor da pizza que você quer 🍕\n\n_Dica: pode pedir meio a meio! Ex: 'meio calabresa meio mussarela'_"

    # Verifica se é seleção numérica dupla (ex: "1 e 2", "1,2")
    two_numbers = parse_two_numbers(message)
    if two_numbers:
        num1, num2 = two_numbers
        pizzas = list(Product.objects.filter(category='PIZZA', active=True).order_by('name'))
        if 1 <= num1 <= len(pizzas) and 1 <= num2 <= len(pizzas):
            pizza1 = pizzas[num1 - 1]
            pizza2 = pizzas[num2 - 1]
            set_conversation_state(phone, "awaiting_half_or_full", {
                "pizza1_id": pizza1.id,
                "pizza2_id": pizza2.id,
                "pizza1_name": pizza1.name,
                "pizza2_name": pizza2.name,
            })
            return (
                f"Você escolheu *{pizza1.name}* e *{pizza2.name}*\n\n"
                f"Como você quer?\n\n"
                f"1️⃣ *Meio a meio* (uma pizza com metade de cada)\n"
                f"2️⃣ *Duas pizzas inteiras* (uma de cada sabor)\n\n"
                f"_'voltar' | 'cancelar'_"
            )

    # Verifica se é pedido de múltiplas pizzas (ex: "2 portuguesa e 4 queijo")
    multiple = parse_multiple_pizzas(message)
    if multiple:
        items = []
        response = "Anotado! ✅\n\n"
        for item in multiple:
            product = item['product']
            qty = item['quantity']
            items.append({
                "type": "single",
                "product_id": product.id,
                "quantity": qty,
                "price": float(product.price)
            })
            response += f"• {qty}x *{product.name}* - R$ {product.price * qty:.2f}\n"

        set_conversation_state(phone, "awaiting_more_items", {
            "order_type": "DELIVERY",
            "items": items
        })

        response += f"\nQuer mais alguma pizza?\n"
        response += f"1️⃣ Quero mais\n"
        response += f"2️⃣ Só isso"
        return response

    # Verifica se é pedido meio a meio
    if is_half_half_request(message):
        return handle_half_half_order(phone, message)

    # Verifica se quer retirada
    if any(word in message_lower for word in ['retirar', 'retirada', 'buscar', 'retira']):
        set_conversation_state(phone, "awaiting_pickup_items", {"order_type": "PICKUP"})
        return "Beleza, vai retirar aqui no local! 👍\n\nQual sabor você quer?"

    # Tenta encontrar um produto na mensagem
    product = find_product_fuzzy(message)
    if product:
        set_conversation_state(phone, "awaiting_observation", {
            "order_type": "DELIVERY",
            "current_item": {
                "type": "single",
                "product_id": product.id,
                "price": float(product.price)
            },
            "items": []
        })
        return (
            f"Boa escolha! 😋 *{product.name}* - R$ {product.price:.2f}\n\n"
            f"Alguma observação? (tirar cebola, sem tomate, etc)\n\n"
            f"_Digite a observação ou 'não' se não tiver_"
        )

    # Saudações - envia boas vindas
    greetings = ['oi', 'ola', 'olá', 'bom dia', 'boa tarde', 'boa noite', 'hey', 'eae', 'eai', 'opa', 'e ai', 'e aí']
    if any(greet in message_lower for greet in greetings):
        return send_welcome_with_menu(phone)

    # Se menciona pizza ou quero sem especificar sabor, mostra cardápio
    if any(word in message_lower for word in ['pizza', 'quero', 'pedir', 'fazer pedido', 'pedido']):
        return handle_menu_request(phone)

    # Mensagem padrão - mostra opções
    return send_welcome_with_menu(phone)


def send_welcome_with_menu(phone: str) -> str:
    """Envia saudação com promoção."""
    settings_obj = BusinessSettings.get_settings()

    welcome = "Boa noite, ja estamos atendendo.\n\n"

    # Adiciona promoção se ativa
    if settings_obj.promo_active and settings_obj.promo_text:
        welcome += "🔥 *PROMOÇÃO:* 2 Pizzas Grandes por R$ 55,00!\n"
        welcome += "(Delivery ou retirada — taxa de entrega conforme o bairro)\n\n"
        welcome += "1️⃣ Quero a promoção (2 pizzas)\n"
        welcome += "2️⃣ Ver cardápio\n"
        welcome += "3️⃣ Já sei o que quero"
    else:
        welcome += "1️⃣ Ver cardápio\n"
        welcome += "2️⃣ Já sei o que quero"

    return welcome


def handle_half_half_order(phone: str, message: str) -> str:
    """Trata pedido de pizza meio a meio."""
    sabor1_text, sabor2_text = parse_half_half(message)

    if sabor1_text and sabor2_text:
        pizza1 = find_product_fuzzy(sabor1_text)
        pizza2 = find_product_fuzzy(sabor2_text)

        if pizza1 and pizza2:
            # Preço da meio a meio: maior preço entre as duas
            preco = max(pizza1.price, pizza2.price)

            set_conversation_state(phone, "awaiting_observation", {
                "order_type": "DELIVERY",
                "current_item": {
                    "type": "half_half",
                    "pizza1_id": pizza1.id,
                    "pizza2_id": pizza2.id,
                    "pizza1_name": pizza1.name,
                    "pizza2_name": pizza2.name,
                    "price": float(preco)
                },
                "items": []
            })

            return (
                f"Boa! 🍕 *Meio a Meio:*\n"
                f"½ {pizza1.name} + ½ {pizza2.name}\n"
                f"💰 R$ {preco:.2f}\n\n"
                f"Alguma observação? (tirar cebola, sem tomate, etc)\n\n"
                f"_Digite a observação ou 'não' se não tiver_"
            )
        elif pizza1:
            # Encontrou só a primeira, pede a segunda
            set_conversation_state(phone, "awaiting_half_half_second", {
                "pizza1_id": pizza1.id,
                "pizza1_name": pizza1.name
            })
            return f"Beleza! Meia *{pizza1.name}*. E a outra metade, qual sabor?"
        elif pizza2:
            # Encontrou só a segunda, pede a primeira
            set_conversation_state(phone, "awaiting_half_half_first", {
                "pizza2_id": pizza2.id,
                "pizza2_name": pizza2.name
            })
            return f"Beleza! Meia *{pizza2.name}*. E a outra metade, qual sabor?"

    # Não conseguiu identificar, inicia fluxo meio a meio
    set_conversation_state(phone, "awaiting_half_half_first", {})

    pizzas = Product.objects.filter(category='PIZZA', active=True).order_by('name')
    menu = "Pizza meio a meio! 🍕\n\nEscolhe o *primeiro* sabor:\n\n"
    for i, pizza in enumerate(pizzas, 1):
        menu += f"{i}. {pizza.name}\n"
    menu += "\n_Digite o número ou nome | 'voltar' | 'sair'_"
    return menu


def handle_half_half_first(phone: str, message: str) -> str:
    """Trata seleção do primeiro sabor da meio a meio."""
    state = get_conversation_state(phone)
    pizza2_id = state["data"].get("pizza2_id")
    pizza2_name = state["data"].get("pizza2_name")

    product = find_product_fuzzy(message)
    if not product:
        return "Hmm, não achei esse sabor 🤔 Pode repetir ou digitar o número?\n\n_'voltar' | 'sair'_"

    if pizza2_id:
        # Já tem o segundo sabor, finaliza
        try:
            pizza2 = Product.objects.get(id=pizza2_id)
            preco = max(product.price, pizza2.price)

            set_conversation_state(phone, "awaiting_observation", {
                "order_type": "DELIVERY",
                "current_item": {
                    "type": "half_half",
                    "pizza1_id": product.id,
                    "pizza2_id": pizza2.id,
                    "pizza1_name": product.name,
                    "pizza2_name": pizza2.name,
                    "price": float(preco)
                },
                "items": []
            })

            return (
                f"Boa! 🍕 *Meio a Meio:*\n"
                f"½ {product.name} + ½ {pizza2.name}\n"
                f"💰 R$ {preco:.2f}\n\n"
                f"Alguma observação? (tirar cebola, sem tomate, etc)\n\n"
                f"_Digite a observação ou 'não' se não tiver_"
            )
        except Product.DoesNotExist:
            pass

    # Pede o segundo sabor
    set_conversation_state(phone, "awaiting_half_half_second", {
        "pizza1_id": product.id,
        "pizza1_name": product.name
    })

    pizzas = Product.objects.filter(category='PIZZA', active=True).order_by('name')
    menu = f"Boa! ½ *{product.name}* ✅\n\nAgora o *segundo* sabor:\n\n"
    for i, pizza in enumerate(pizzas, 1):
        menu += f"{i}. {pizza.name}\n"
    menu += "\n_Digite o número ou nome | 'voltar' | 'sair'_"
    return menu


def handle_half_half_second(phone: str, message: str) -> str:
    """Trata seleção do segundo sabor da meio a meio."""
    state = get_conversation_state(phone)
    pizza1_id = state["data"].get("pizza1_id")
    pizza1_name = state["data"].get("pizza1_name")

    product = find_product_fuzzy(message)
    if not product:
        return "Hmm, não achei esse sabor 🤔 Pode repetir ou digitar o número?\n\n_'voltar' | 'sair'_"

    try:
        pizza1 = Product.objects.get(id=pizza1_id)
        preco = max(pizza1.price, product.price)

        set_conversation_state(phone, "awaiting_observation", {
            "order_type": "DELIVERY",
            "current_item": {
                "type": "half_half",
                "pizza1_id": pizza1.id,
                "pizza2_id": product.id,
                "pizza1_name": pizza1.name,
                "pizza2_name": product.name,
                "price": float(preco)
            },
            "items": []
        })

        return (
            f"Boa! 🍕 *Meio a Meio:*\n"
            f"½ {pizza1.name} + ½ {product.name}\n"
            f"💰 R$ {preco:.2f}\n\n"
            f"Alguma observação? (tirar cebola, sem tomate, etc)\n\n"
            f"_Digite a observação ou 'não' se não tiver_"
        )
    except Product.DoesNotExist:
        clear_conversation_state(phone)
        return "Ops, algo deu errado 😅 Vamos recomeçar!"


def handle_observation(phone: str, message: str) -> str:
    """Trata observação do item (tirar ingredientes, etc)."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    current_item = state["data"].get("current_item", {})
    items = state["data"].get("items", [])
    order_type = state["data"].get("order_type", "DELIVERY")

    # Salva observação no item atual
    if message_lower not in ['nao', 'não', 'n', 'nenhuma', 'nada']:
        current_item["observation"] = message

    items.append(current_item)

    set_conversation_state(phone, "awaiting_more_items", {
        "items": items,
        "order_type": order_type
    })

    # Monta nome do item para exibição
    if current_item.get("type") == "half_half":
        item_name = f"½ {current_item['pizza1_name']} + ½ {current_item['pizza2_name']}"
    else:
        try:
            product = Product.objects.get(id=current_item["product_id"])
            item_name = product.name
        except:
            item_name = "Pizza"

    obs_text = f"\n📝 Obs: {current_item.get('observation', '')}" if current_item.get('observation') else ""

    return (
        f"Anotado! ✅ *{item_name}*{obs_text}\n\n"
        f"Quer mais alguma pizza?\n"
        f"1️⃣ Quero mais\n"
        f"2️⃣ Só isso"
    )


def handle_promo_order(phone: str) -> str:
    """Inicia pedido da promoção (2 pizzas por R$ 55)."""
    pizzas = Product.objects.filter(category='PIZZA', active=True).order_by('name')

    menu = "Boa escolha! 🔥 *2 Pizzas Grandes por R$ 55,00*\n\n"
    menu += "Escolhe o *primeiro* sabor:\n\n"
    for i, pizza in enumerate(pizzas, 1):
        menu += f"{i}. {pizza.name}\n"

    menu += "\n_Digite o número ou nome | 'voltar' | 'sair'_"

    set_conversation_state(phone, "awaiting_promo_pizza_1", {"promo": True})
    return menu


def handle_promo_pizza_1(phone: str, message: str) -> str:
    """Trata seleção da primeira pizza da promoção."""
    # Verifica se digitou dois números (ex: "1 e 2", "1,2")
    two_numbers = parse_two_numbers(message)
    if two_numbers:
        num1, num2 = two_numbers
        pizzas = list(Product.objects.filter(category='PIZZA', active=True).order_by('name'))
        if 1 <= num1 <= len(pizzas) and 1 <= num2 <= len(pizzas):
            pizza1 = pizzas[num1 - 1]
            pizza2 = pizzas[num2 - 1]
            set_conversation_state(phone, "awaiting_promo_half_or_full", {
                "promo": True,
                "pizza1_id": pizza1.id,
                "pizza2_id": pizza2.id,
                "pizza1_name": pizza1.name,
                "pizza2_name": pizza2.name,
            })
            return (
                f"Você escolheu *{pizza1.name}* e *{pizza2.name}*\n\n"
                f"Como você quer na promoção?\n\n"
                f"1️⃣ *Meio a meio* (uma pizza com metade de cada + uma inteira)\n"
                f"2️⃣ *Duas pizzas inteiras* (uma de cada sabor)\n\n"
                f"_'voltar' | 'cancelar'_"
            )

    product = find_product_fuzzy(message)
    if not product:
        return "Hmm, não achei esse sabor 🤔 Pode repetir ou digitar o número do cardápio?\n\n_Dica: pode digitar '1 e 2' para escolher dois sabores!_\n\n_'voltar' | 'sair'_"

    pizzas = Product.objects.filter(category='PIZZA', active=True).order_by('name')

    menu = f"Boa! ✅ Primeira pizza: *{product.name}*\n\n"
    menu += "Agora escolhe o *segundo* sabor:\n\n"
    for i, pizza in enumerate(pizzas, 1):
        menu += f"{i}. {pizza.name}\n"

    menu += "\n_Dica: pode digitar '1 e 2' para meio a meio!_\n"
    menu += "_Digite o número ou nome | 'voltar' | 'sair'_"

    set_conversation_state(phone, "awaiting_promo_pizza_2", {
        "promo": True,
        "promo_pizza_1": product.id
    })
    return menu


def handle_promo_half_or_full(phone: str, message: str) -> str:
    """Trata escolha entre meio a meio ou duas pizzas inteiras na promoção."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    pizza1_id = state["data"].get("pizza1_id")
    pizza2_id = state["data"].get("pizza2_id")
    pizza1_name = state["data"].get("pizza1_name")
    pizza2_name = state["data"].get("pizza2_name")

    try:
        pizza1 = Product.objects.get(id=pizza1_id)
        pizza2 = Product.objects.get(id=pizza2_id)
    except Product.DoesNotExist:
        clear_conversation_state(phone)
        return "Ops, algo deu errado 😅 Vamos recomeçar!"

    promo_price = Decimal('27.50')

    # Meio a meio - uma pizza meio a meio + precisa escolher a segunda
    if message_lower in ['1', 'meio', 'metade', 'meio a meio', 'meia']:
        preco = max(pizza1.price, pizza2.price)
        set_conversation_state(phone, "awaiting_promo_second_after_half", {
            "promo": True,
            "items": [{
                "type": "half_half",
                "pizza1_id": pizza1.id,
                "pizza2_id": pizza2.id,
                "pizza1_name": pizza1.name,
                "pizza2_name": pizza2.name,
                "price": float(promo_price),
                "promo_price": float(promo_price)
            }]
        })
        pizzas = Product.objects.filter(category='PIZZA', active=True).order_by('name')
        menu = (
            f"Boa! 🍕 Primeira pizza: *Meio a Meio*\n"
            f"½ {pizza1.name} + ½ {pizza2.name}\n\n"
            f"Agora escolhe o sabor da *segunda pizza* da promoção:\n\n"
        )
        for i, pizza in enumerate(pizzas, 1):
            menu += f"{i}. {pizza.name}\n"
        menu += "\n_Digite o número ou nome | 'voltar' | 'sair'_"
        return menu

    # Duas pizzas inteiras
    if message_lower in ['2', 'duas', 'inteira', 'inteiras', 'separadas', 'separado']:
        items = [
            {"product_id": pizza1.id, "quantity": 1, "promo_price": float(promo_price)},
            {"product_id": pizza2.id, "quantity": 1, "promo_price": float(promo_price)}
        ]
        set_conversation_state(phone, "awaiting_promo_order_type", {
            "items": items,
            "promo": True,
            "pizza_1_name": pizza1.name,
            "pizza_2_name": pizza2.name
        })
        return (
            f"Perfeito! ✅\n\n"
            f"🍕 *{pizza1.name}* + *{pizza2.name}*\n"
            f"💰 *Total da promoção: R$ 55,00*\n\n"
            f"Vai ser pra *entrega* ou *retirada*? 🛵🏪\n\n"
            f"1️⃣ Entrega (delivery)\n"
            f"2️⃣ Retirada no local\n\n"
            f"_'voltar' | 'sair'_"
        )

    return "Não entendi 😅 Digite 1 para meio a meio ou 2 para duas pizzas inteiras.\n\n_'voltar' | 'cancelar'_"


def handle_promo_second_after_half(phone: str, message: str) -> str:
    """Trata seleção da segunda pizza após escolher meio a meio na promoção."""
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])

    product = find_product_fuzzy(message)
    if not product:
        return "Hmm, não achei esse sabor 🤔 Pode repetir ou digitar o número do cardápio?\n\n_'voltar' | 'sair'_"

    promo_price = Decimal('27.50')
    items.append({"product_id": product.id, "quantity": 1, "promo_price": float(promo_price)})

    # Monta nomes para exibição
    half_half = items[0]
    pizza1_name = half_half.get("pizza1_name", "")
    pizza2_name = half_half.get("pizza2_name", "")

    set_conversation_state(phone, "awaiting_promo_order_type", {
        "items": items,
        "promo": True,
        "pizza_1_name": f"½ {pizza1_name} + ½ {pizza2_name}",
        "pizza_2_name": product.name
    })

    return (
        f"Perfeito! ✅ Segunda pizza: *{product.name}*\n\n"
        f"🍕 *½ {pizza1_name} + ½ {pizza2_name}* (meio a meio)\n"
        f"🍕 *{product.name}*\n"
        f"💰 *Total da promoção: R$ 55,00*\n\n"
        f"Vai ser pra *entrega* ou *retirada*? 🛵🏪\n\n"
        f"1️⃣ Entrega (delivery)\n"
        f"2️⃣ Retirada no local\n\n"
        f"_'voltar' | 'sair'_"
    )


def handle_promo_pizza_2(phone: str, message: str) -> str:
    """Trata seleção da segunda pizza da promoção."""
    state = get_conversation_state(phone)
    pizza_1_id = state["data"].get("promo_pizza_1")
    logger.info(f"DEBUG handle_promo_pizza_2: message={repr(message)}, isdigit={message.strip().isdigit()}, pizza_1_id={pizza_1_id}")

    product = find_product_fuzzy(message)
    if not product:
        logger.warning(f"DEBUG: find_product_fuzzy retornou None para '{message}'")
        return "Hmm, não achei esse sabor 🤔 Pode repetir ou digitar o número do cardápio?\n\n_'voltar' | 'sair'_"

    try:
        pizza_1 = Product.objects.get(id=pizza_1_id)
    except Product.DoesNotExist:
        clear_conversation_state(phone)
        return "Ops, algo deu errado 😅 Vamos recomeçar!"

    # Define os itens com preço especial da promoção (R$ 27,50 cada = R$ 55 total)
    promo_price = Decimal('27.50')
    items = [
        {"product_id": pizza_1.id, "quantity": 1, "promo_price": float(promo_price)},
        {"product_id": product.id, "quantity": 1, "promo_price": float(promo_price)}
    ]

    set_conversation_state(phone, "awaiting_promo_order_type", {
        "items": items,
        "promo": True,
        "pizza_1_name": pizza_1.name,
        "pizza_2_name": product.name
    })

    return (
        f"Perfeito! ✅ Segunda pizza: *{product.name}*\n\n"
        f"🍕 *{pizza_1.name}* + *{product.name}*\n"
        f"💰 *Total da promoção: R$ 55,00*\n\n"
        f"Vai ser pra *entrega* ou *retirada*? 🛵🏪\n\n"
        f"1️⃣ Entrega (delivery)\n"
        f"2️⃣ Retirada no local\n\n"
        f"_'voltar' | 'sair'_"
    )


def handle_promo_order_type(phone: str, message: str) -> str:
    """Trata escolha de entrega ou retirada na promoção."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])

    # Entrega
    if message_lower in ['1', 'entrega', 'delivery', 'entregar']:
        set_conversation_state(phone, "awaiting_drink", {
            "items": items,
            "order_type": "DELIVERY",
            "promo": True
        })
        return get_drinks_menu()

    # Retirada
    if message_lower in ['2', 'retirada', 'retirar', 'buscar', 'pickup']:
        set_conversation_state(phone, "awaiting_drink_pickup", {
            "items": items,
            "order_type": "PICKUP",
            "promo": True
        })
        return get_drinks_menu()

    return "Não entendi 😅 Digita 1 pra entrega ou 2 pra retirada!\n\n_'voltar' | 'sair'_"


def handle_awaiting_more_items(phone: str, message: str) -> str:
    """Trata pergunta se quer mais itens."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])
    order_type = state["data"].get("order_type", "DELIVERY")

    # Verifica se quer mais pizza
    if message_lower in ['1', 'sim', 's', 'quero', 'mais']:
        set_conversation_state(phone, "awaiting_another_item", {"items": items, "order_type": order_type})

        # Mostra cardápio resumido
        pizzas = Product.objects.filter(category='PIZZA', active=True).order_by('name')
        menu = "Beleza! Qual outro sabor? 🍕\n\n"
        for i, pizza in enumerate(pizzas, 1):
            menu += f"{i}. {pizza.name} - R$ {pizza.price:.2f}\n"
        menu += "\n_Digite o número ou nome | 'voltar' | 'sair'_"
        return menu

    # Verifica se não quer mais
    if message_lower in ['2', 'nao', 'não', 'n', 'so isso', 'só isso', 'essa', 'so essa', 'só essa']:
        set_conversation_state(phone, "awaiting_drink", {"items": items, "order_type": order_type})
        return get_drinks_menu()

    # Tenta identificar se digitou o nome de uma pizza diretamente
    product = find_product_fuzzy(message)
    if product:
        items.append({"product_id": product.id, "quantity": 1})
        set_conversation_state(phone, "awaiting_more_items", {"items": items, "order_type": order_type})
        return (
            f"Anotado! ✅ *{product.name}* - R$ {product.price:.2f}\n\n"
            f"Mais alguma pizza?\n"
            f"1️⃣ Quero mais\n"
            f"2️⃣ Só isso"
        )

    return "Não entendi 😅 Digita 1 pra adicionar mais pizza ou 2 pra continuar!\n\n_'voltar' | 'sair'_"


def handle_awaiting_another_item(phone: str, message: str) -> str:
    """Trata adicao de mais um item."""
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])
    order_type = state["data"].get("order_type", "DELIVERY")

    # Verifica se é pedido meio a meio
    if is_half_half_request(message):
        sabor1_text, sabor2_text = parse_half_half(message)
        if sabor1_text and sabor2_text:
            pizza1 = find_product_fuzzy(sabor1_text)
            pizza2 = find_product_fuzzy(sabor2_text)
            if pizza1 and pizza2:
                preco = max(pizza1.price, pizza2.price)
                set_conversation_state(phone, "awaiting_observation", {
                    "order_type": order_type,
                    "current_item": {
                        "type": "half_half",
                        "pizza1_id": pizza1.id,
                        "pizza2_id": pizza2.id,
                        "pizza1_name": pizza1.name,
                        "pizza2_name": pizza2.name,
                        "price": float(preco)
                    },
                    "items": items
                })
                return (
                    f"Boa! 🍕 *Meio a Meio:*\n"
                    f"½ {pizza1.name} + ½ {pizza2.name}\n"
                    f"💰 R$ {preco:.2f}\n\n"
                    f"Alguma observação? (tirar cebola, sem tomate, etc)\n\n"
                    f"_Digite a observação ou 'não' se não tiver_"
                )

        # Inicia fluxo de meio a meio
        set_conversation_state(phone, "awaiting_half_half_first", {"items": items, "order_type": order_type})
        pizzas = Product.objects.filter(category='PIZZA', active=True).order_by('name')
        menu = "Pizza meio a meio! 🍕\n\nEscolhe o *primeiro* sabor:\n\n"
        for i, pizza in enumerate(pizzas, 1):
            menu += f"{i}. {pizza.name}\n"
        menu += "\n_Digite o número ou nome | 'voltar' | 'sair'_"
        return menu

    product = find_product_fuzzy(message)
    if not product:
        return "Hmm, não achei esse sabor 🤔 Pode repetir ou digitar o número do cardápio?\n\n_Dica: pode pedir meio a meio! Ex: 'meio calabresa meio mussarela'_\n\n_'voltar' | 'sair'_"

    set_conversation_state(phone, "awaiting_observation", {
        "order_type": order_type,
        "current_item": {
            "type": "single",
            "product_id": product.id,
            "price": float(product.price)
        },
        "items": items
    })

    return (
        f"Boa! ✅ *{product.name}* - R$ {product.price:.2f}\n\n"
        f"Alguma observação? (tirar cebola, sem tomate, etc)\n\n"
        f"_Digite a observação ou 'não' se não tiver_"
    )


def handle_awaiting_items(phone: str, message: str, order_type: str) -> str:
    """Trata selecao de itens para retirada."""
    product = find_product_fuzzy(message)
    if not product:
        return "Hmm, não achei esse sabor 🤔 Pode repetir ou digitar o número do cardápio?\n\n_'voltar' | 'sair'_"

    state = get_conversation_state(phone)
    items = state["data"].get("items", [])
    items.append({"product_id": product.id, "quantity": 1})

    set_conversation_state(phone, "awaiting_more_items_pickup", {
        "items": items,
        "order_type": order_type
    })

    return (
        f"Anotado! ✅ *{product.name}* - R$ {product.price:.2f}\n\n"
        f"Mais alguma pizza?\n"
        f"1️⃣ Quero mais\n"
        f"2️⃣ Só isso"
    )


def handle_awaiting_more_items_pickup(phone: str, message: str) -> str:
    """Trata pergunta se quer mais itens (retirada)."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])

    # Verifica se quer mais pizza
    if message_lower in ['1', 'sim', 's', 'quero', 'mais']:
        set_conversation_state(phone, "awaiting_pickup_items", {"items": items, "order_type": "PICKUP"})

        # Mostra cardápio resumido
        pizzas = Product.objects.filter(category='PIZZA', active=True).order_by('name')
        menu = "Beleza! Qual outro sabor? 🍕\n\n"
        for i, pizza in enumerate(pizzas, 1):
            menu += f"{i}. {pizza.name} - R$ {pizza.price:.2f}\n"
        menu += "\n_Digite o número ou nome | 'voltar' | 'sair'_"
        return menu

    # Verifica se não quer mais
    if message_lower in ['2', 'nao', 'não', 'n', 'so isso', 'só isso', 'essa', 'so essa', 'só essa']:
        set_conversation_state(phone, "awaiting_drink_pickup", {"items": items, "order_type": "PICKUP"})
        return get_drinks_menu()

    # Tenta identificar se digitou o nome de uma pizza diretamente
    product = find_product_fuzzy(message)
    if product:
        items.append({"product_id": product.id, "quantity": 1})
        set_conversation_state(phone, "awaiting_more_items_pickup", {"items": items, "order_type": "PICKUP"})
        return (
            f"Anotado! ✅ *{product.name}* - R$ {product.price:.2f}\n\n"
            f"Mais alguma pizza?\n"
            f"1️⃣ Quero mais\n"
            f"2️⃣ Só isso"
        )

    return "Não entendi 😅 Digita 1 pra adicionar mais pizza ou 2 pra continuar!\n\n_'voltar' | 'sair'_"


def handle_awaiting_drink(phone: str, message: str) -> str:
    """Trata selecao de bebida para entrega."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])

    drinks = list(Product.objects.filter(category='BEBIDA', active=True)[:4])
    no_drink_option = str(len(drinks) + 1)

    # Verifica se não quer bebida
    if message_lower in [no_drink_option, "nao", "não", "n", "nao obrigado", "não obrigado", "so pizza", "só pizza"]:
        set_conversation_state(phone, "awaiting_address", {"items": items})
        return "Beleza! 📍 Me passa o endereço completo pra entrega:\n(Rua, número e bairro)\n\n_'voltar' | 'sair'_"

    # Tenta encontrar a bebida
    drink = find_drink_by_option(message)
    if drink:
        items.append({"product_id": drink.id, "quantity": 1})
        set_conversation_state(phone, "awaiting_address", {"items": items})
        return f"Boa! ✅ *{drink.name}* adicionado!\n\n📍 Me passa o endereço completo pra entrega:\n(Rua, número e bairro)\n\n_'voltar' | 'sair'_"

    # Não encontrou bebida válida
    return f"Não entendi 😅 Escolhe uma opção de 1 a {len(drinks)}, ou {no_drink_option} se não quiser bebida!\n\n_'voltar' | 'sair'_"


def handle_awaiting_drink_pickup(phone: str, message: str) -> str:
    """Trata selecao de bebida para retirada."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])
    is_promo = state["data"].get("promo", False)

    drinks = list(Product.objects.filter(category='BEBIDA', active=True)[:4])
    no_drink_option = str(len(drinks) + 1)

    # Verifica se não quer bebida
    if message_lower in [no_drink_option, "nao", "não", "n", "nao obrigado", "não obrigado", "so pizza", "só pizza"]:
        set_conversation_state(phone, "confirming_pickup", {"items": items, "promo": is_promo})
        summary = format_order_summary(items, order_type='PICKUP', is_promo=is_promo)
        return (
            f"Beleza! Olha o resumo do seu pedido:\n\n"
            f"{summary}\n\n"
            f"Tudo certo? Você vai *RETIRAR* aqui no local 🏪\n"
            f"1️⃣ Confirmar pedido\n"
            f"2️⃣ Cancelar"
        )

    # Tenta encontrar a bebida
    drink = find_drink_by_option(message)
    if drink:
        items.append({"product_id": drink.id, "quantity": 1})
        set_conversation_state(phone, "confirming_pickup", {"items": items, "promo": is_promo})
        summary = format_order_summary(items, order_type='PICKUP', is_promo=is_promo)
        return (
            f"Boa! ✅ *{drink.name}* adicionado!\n\n"
            f"Olha o resumo do seu pedido:\n\n"
            f"{summary}\n\n"
            f"Tudo certo? Você vai *RETIRAR* aqui no local 🏪\n"
            f"1️⃣ Confirmar pedido\n"
            f"2️⃣ Cancelar"
        )

    return f"Não entendi 😅 Escolhe uma opção de 1 a {len(drinks)}, ou {no_drink_option} se não quiser bebida!\n\n_'voltar' | 'sair'_"


def handle_confirming_pickup(phone: str, message: str) -> str:
    """Trata confirmação do pedido de retirada."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])

    if message_lower in ['1', 'sim', 's', 'confirmar', 'confirma', 'ok', 'bora']:
        customer = get_or_create_customer(phone)

        order = Order.objects.create(
            customer=customer,
            order_type='PICKUP',
            status='PREPARING',
            payment_status='PAY_ON_DELIVERY'
        )

        for item_data in items:
            item_type = item_data.get("type", "single")
            obs = item_data.get("observation", "")
            qty = item_data.get("quantity", 1)

            if item_type == "half_half":
                # Pizza meio a meio
                pizza1_id = item_data.get("pizza1_id")
                pizza1_name = item_data.get("pizza1_name", "")
                pizza2_name = item_data.get("pizza2_name", "")

                product = Product.objects.get(id=pizza1_id)
                unit_price = Decimal(str(item_data.get("price", product.price)))

                notes_parts = [f"MEIO A MEIO: ½ {pizza1_name} + ½ {pizza2_name}"]
                if obs:
                    notes_parts.append(obs)

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=qty,
                    unit_price=unit_price,
                    notes=" | ".join(notes_parts)
                )
            else:
                # Pizza normal
                product = Product.objects.get(id=item_data["product_id"])
                if "promo_price" in item_data:
                    unit_price = Decimal(str(item_data["promo_price"]))
                elif "price" in item_data:
                    unit_price = Decimal(str(item_data["price"]))
                else:
                    unit_price = product.price

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=qty,
                    unit_price=unit_price,
                    notes=obs
                )

        order.calculate_totals()
        order.save()

        clear_conversation_state(phone)

        return (
            f"Pedido #{order.id} confirmado! ✅🍕\n\n"
            f"Já tô preparando! Quando ficar pronto eu te aviso aqui, beleza?\n\n"
            f"A Pizzaria do Negão agradece! ❤️"
        )

    if message_lower in ['2', 'nao', 'não', 'n', 'cancelar']:
        clear_conversation_state(phone)
        return "Sem problemas! Pedido cancelado. Qualquer coisa é só chamar! 👋"

    return "Digita 1 pra confirmar ou 2 pra cancelar 😊\n\n_'voltar' | 'sair'_"


def handle_awaiting_address(phone: str, message: str) -> str:
    """Trata endereco de entrega."""
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])
    is_promo = state["data"].get("promo", False)

    # Verifica se o endereço é muito curto
    if len(message.strip()) < 10:
        return "Preciso do endereço completo 😅\nMe passa a rua, número e bairro!\n\n_'voltar' | 'sair'_"

    # Tenta identificar o bairro no endereço
    words = message.lower().split()
    neighborhood = None
    fee_obj = None

    for word in words:
        fee_obj = find_neighborhood_fee(word)
        if fee_obj:
            neighborhood = fee_obj.neighborhood
            break

    if not neighborhood:
        fee_obj = DeliveryFee.objects.filter(active=True).first()
        neighborhood = fee_obj.neighborhood if fee_obj else "Centro"

    delivery_fee = fee_obj.fee if fee_obj else Decimal('5.00')

    set_conversation_state(phone, "confirming_delivery", {
        "items": items,
        "address": message,
        "neighborhood": neighborhood,
        "delivery_fee": float(delivery_fee),
        "promo": is_promo
    })

    summary = format_order_summary(items, delivery_fee, order_type='DELIVERY', is_promo=is_promo)

    return (
        f"Beleza! Olha o resumo do seu pedido:\n\n"
        f"{summary}\n\n"
        f"📍 *Endereço:* {message}\n"
        f"🏘️ *Bairro:* {neighborhood}\n\n"
        f"Tudo certo pra *ENTREGA*? 🛵\n"
        f"1️⃣ Confirmar pedido\n"
        f"2️⃣ Cancelar"
    )


def handle_confirming_delivery(phone: str, message: str) -> str:
    """Trata confirmação do pedido de entrega."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])
    address = state["data"].get("address", "")
    neighborhood = state["data"].get("neighborhood", "Centro")
    delivery_fee = Decimal(str(state["data"].get("delivery_fee", 5.00)))

    if message_lower in ['1', 'sim', 's', 'confirmar', 'confirma', 'ok', 'bora']:
        customer = get_or_create_customer(phone)
        customer.address = address
        customer.neighborhood = neighborhood
        customer.save()

        order = Order.objects.create(
            customer=customer,
            order_type='DELIVERY',
            delivery_address=address,
            neighborhood=neighborhood,
            delivery_fee=delivery_fee,
            status='AWAITING_PAYMENT'
        )

        for item_data in items:
            item_type = item_data.get("type", "single")
            obs = item_data.get("observation", "")
            qty = item_data.get("quantity", 1)

            if item_type == "half_half":
                # Pizza meio a meio - usa o primeiro produto como referência
                pizza1_id = item_data.get("pizza1_id")
                pizza2_id = item_data.get("pizza2_id")
                pizza1_name = item_data.get("pizza1_name", "")
                pizza2_name = item_data.get("pizza2_name", "")

                product = Product.objects.get(id=pizza1_id)
                unit_price = Decimal(str(item_data.get("price", product.price)))

                # Monta observação com info de meio a meio
                notes_parts = [f"MEIO A MEIO: ½ {pizza1_name} + ½ {pizza2_name}"]
                if obs:
                    notes_parts.append(obs)

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=qty,
                    unit_price=unit_price,
                    notes=" | ".join(notes_parts)
                )
            else:
                # Pizza normal
                product = Product.objects.get(id=item_data["product_id"])
                # Usa preço promocional se existir
                if "promo_price" in item_data:
                    unit_price = Decimal(str(item_data["promo_price"]))
                elif "price" in item_data:
                    unit_price = Decimal(str(item_data["price"]))
                else:
                    unit_price = product.price

                OrderItem.objects.create(
                    order=order,
                    product=product,
                    quantity=qty,
                    unit_price=unit_price,
                    notes=obs
                )

        order.calculate_totals()
        order.save()

        set_conversation_state(phone, "awaiting_receipt", {"order_id": order.id})

        settings_obj = BusinessSettings.get_settings()

        return (
            f"Pedido #{order.id} confirmado! ✅\n\n"
            f"💰 *Pagamento via PIX:*\n"
            f"Chave: *{settings_obj.pix_key}*\n"
            f"Nome: {settings_obj.pix_name}\n\n"
            f"Me manda o *comprovante* (foto) aqui pra eu liberar seu pedido! 📸\n\n"
            f"_Ou se preferir, digita 'pagar na entrega'_"
        )

    if message_lower in ['2', 'nao', 'não', 'n', 'cancelar']:
        clear_conversation_state(phone)
        return "Sem problemas! Pedido cancelado. Qualquer coisa é só chamar! 👋"

    return "Digita 1 pra confirmar ou 2 pra cancelar 😊\n\n_'voltar' | 'sair'_"


def handle_awaiting_receipt(phone: str, message: str, msg_type: str, media_url: str = None) -> str:
    """Trata recebimento do comprovante."""
    state = get_conversation_state(phone)
    order_id = state["data"].get("order_id")

    if not order_id:
        clear_conversation_state(phone)
        return "Ops, algo deu errado 😅 Faz um novo pedido aí!"

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        clear_conversation_state(phone)
        return "Não achei esse pedido 🤔 Faz um novo aí!"

    message_lower = message.lower().strip() if message else ""

    # Verifica se é uma imagem ou documento (comprovante)
    if msg_type in ['image', 'document', 'file'] or media_url:
        if media_url:
            try:
                # Corrige URL para funcionar dentro do Docker
                # Substitui localhost:3000 pelo WAHA_URL configurado
                corrected_url = media_url
                if 'localhost:3000' in media_url:
                    corrected_url = media_url.replace('http://localhost:3000', WAHA_URL)
                elif '127.0.0.1:3000' in media_url:
                    corrected_url = media_url.replace('http://127.0.0.1:3000', WAHA_URL)

                from .waha_service import WAHA_API_KEY
                import mimetypes
                headers = {'X-Api-Key': WAHA_API_KEY}
                logger.info(f"Baixando comprovante de: {corrected_url}")
                response = requests.get(corrected_url, headers=headers, timeout=30)
                if response.status_code == 200:
                    # Detecta extensão pelo Content-Type ou URL
                    content_type = response.headers.get('Content-Type', '')
                    if 'pdf' in content_type or corrected_url.lower().endswith('.pdf'):
                        ext = 'pdf'
                    elif 'png' in content_type or corrected_url.lower().endswith('.png'):
                        ext = 'png'
                    elif 'gif' in content_type or corrected_url.lower().endswith('.gif'):
                        ext = 'gif'
                    elif 'webp' in content_type or corrected_url.lower().endswith('.webp'):
                        ext = 'webp'
                    else:
                        ext = 'jpg'

                    filename = f"receipt_{order.id}.{ext}"
                    order.payment_receipt.save(filename, ContentFile(response.content))
                    logger.info(f"Comprovante salvo: {filename} (Content-Type: {content_type})")
                else:
                    logger.warning(f"Falha ao baixar comprovante: {response.status_code}")
            except Exception as e:
                logger.error(f"Erro ao baixar comprovante: {e}")

        order.payment_status = 'RECEIPT_RECEIVED'
        # Mantém status aguardando pagamento até o dono aprovar
        order.status = 'AWAITING_PAYMENT'
        order.save()

        clear_conversation_state(phone)

        return (
            f"Comprovante recebido! ✅\n\n"
            f"Seu pedido #{order.id} está sendo analisado. 🔍\n\n"
            f"Assim que o pagamento for confirmado, te aviso aqui e já começo a preparar! 🍕\n\n"
            f"A Pizzaria do Negão agradece pela preferência! ❤️"
        )

    # Permite pagar na entrega
    if any(word in message_lower for word in ['pagar na entrega', 'pago na entrega', 'na entrega', 'entrega']):
        set_conversation_state(phone, "awaiting_payment_method", {"order_id": order.id})
        return (
            f"Beleza! Como vai ser o pagamento na entrega?\n\n"
            f"1️⃣ Dinheiro 💵\n"
            f"2️⃣ Cartão 💳 (taxa de R$ 2,00 da maquininha)\n\n"
            f"_'voltar' | 'cancelar'_"
        )

    # Pagamento em dinheiro
    if any(word in message_lower for word in ['dinheiro', 'din', 'especie', 'espécie']):
        set_conversation_state(phone, "awaiting_change", {"order_id": order.id})
        return (
            f"Pagamento em *dinheiro* 💵\n\n"
            f"Vai precisar de troco? Se sim, pra quanto?\n\n"
            f"_Ex: 'troco pra 100' ou 'não precisa'_"
        )

    # Pagamento em cartão
    if any(word in message_lower for word in ['cartao', 'cartão', 'credito', 'crédito', 'debito', 'débito']):
        set_conversation_state(phone, "awaiting_card_type", {"order_id": order.id})
        return (
            f"Pagamento em *cartão* 💳\n\n"
            f"⚠️ Taxa de R$ 2,00 da maquininha\n\n"
            f"Vai ser:\n"
            f"1️⃣ Crédito\n"
            f"2️⃣ Débito\n\n"
            f"_'voltar' | 'cancelar'_"
        )

    # Opção de ver resumo do pedido
    if any(word in message_lower for word in ['resumo', 'pedido', 'total']):
        items_data = []
        for item in order.items.all():
            items_data.append({"product_id": item.product.id, "quantity": item.quantity})
        summary = format_order_summary(items_data, order.delivery_fee, order_type='DELIVERY')
        return f"{summary}\n\nTô esperando o comprovante! 📸\n\n_Ou digita 'pagar na entrega' se preferir_"

    return (
        f"Tô esperando o comprovante do PIX! 📸\n\n"
        f"Pode mandar a foto aqui, ou se preferir:\n"
        f"• Digita *'pagar na entrega'* pra pagar quando chegar\n"
        f"• Digita *'cancelar'* se quiser desistir"
    )


def handle_payment_method(phone: str, message: str) -> str:
    """Trata escolha de forma de pagamento na entrega."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    order_id = state["data"].get("order_id")

    if message_lower in ['1', 'dinheiro', 'din', 'especie', 'espécie']:
        set_conversation_state(phone, "awaiting_change", {"order_id": order_id})
        return (
            f"Pagamento em *dinheiro* 💵\n\n"
            f"Vai precisar de troco? Se sim, pra quanto?\n\n"
            f"_Ex: 'troco pra 100' ou 'não precisa'_"
        )

    if message_lower in ['2', 'cartao', 'cartão', 'card']:
        set_conversation_state(phone, "awaiting_card_type", {"order_id": order_id})
        return (
            f"Pagamento em *cartão* 💳\n\n"
            f"⚠️ Taxa de R$ 2,00 da maquininha\n\n"
            f"Vai ser:\n"
            f"1️⃣ Crédito\n"
            f"2️⃣ Débito\n\n"
            f"_'voltar' | 'cancelar'_"
        )

    return "Não entendi 😅 Digita 1 pra dinheiro ou 2 pra cartão!\n\n_'voltar' | 'cancelar'_"


def handle_awaiting_change(phone: str, message: str) -> str:
    """Trata informação sobre troco."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    order_id = state["data"].get("order_id")

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        clear_conversation_state(phone)
        return "Ops, algo deu errado 😅 Faz um novo pedido aí!"

    # Verifica se não precisa de troco
    if any(word in message_lower for word in ['nao', 'não', 'n', 'nao precisa', 'não precisa', 'sem troco', 'tenho trocado']):
        order.payment_status = 'PAY_ON_DELIVERY'
        order.payment_method = 'CASH'
        order.status = 'PREPARING'
        order.save()

        clear_conversation_state(phone)
        settings_obj = BusinessSettings.get_settings()
        return (
            f"Beleza! Pedido #{order.id} confirmado! 💵\n\n"
            f"Pagamento: *Dinheiro* (sem troco)\n\n"
            f"⏱️ Previsão: {settings_obj.min_delivery_time} a {settings_obj.max_delivery_time} min\n\n"
            f"Quando sair pra entrega eu te aviso aqui!\n\n"
            f"A Pizzaria do Negão agradece! ❤️"
        )

    # Extrai valor do troco
    import re
    numbers = re.findall(r'\d+', message)
    if numbers:
        change_for = int(numbers[0])
        order.payment_status = 'PAY_ON_DELIVERY'
        order.payment_method = 'CASH'
        order.change_for = Decimal(str(change_for))
        order.status = 'PREPARING'
        order.save()

        clear_conversation_state(phone)
        settings_obj = BusinessSettings.get_settings()
        return (
            f"Beleza! Pedido #{order.id} confirmado! 💵\n\n"
            f"Pagamento: *Dinheiro*\n"
            f"💰 Troco pra: R$ {change_for},00\n\n"
            f"⏱️ Previsão: {settings_obj.min_delivery_time} a {settings_obj.max_delivery_time} min\n\n"
            f"Quando sair pra entrega eu te aviso aqui!\n\n"
            f"A Pizzaria do Negão agradece! ❤️"
        )

    return "Não entendi 😅 Me diz o valor pro troco (ex: 'troco pra 50') ou 'não precisa'"


def handle_card_type(phone: str, message: str) -> str:
    """Trata escolha de crédito ou débito."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    order_id = state["data"].get("order_id")

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        clear_conversation_state(phone)
        return "Ops, algo deu errado 😅 Faz um novo pedido aí!"

    card_type = None
    if message_lower in ['1', 'credito', 'crédito', 'cred']:
        card_type = 'CREDIT'
        card_name = 'Crédito'
    elif message_lower in ['2', 'debito', 'débito', 'deb']:
        card_type = 'DEBIT'
        card_name = 'Débito'
    else:
        return "Não entendi 😅 Digita 1 pra crédito ou 2 pra débito!\n\n_'voltar' | 'cancelar'_"

    order.payment_status = 'PAY_ON_DELIVERY'
    order.payment_method = card_type
    order.status = 'PREPARING'
    # Adiciona taxa da maquininha
    order.card_fee = Decimal('2.00')
    order.save()

    clear_conversation_state(phone)
    settings_obj = BusinessSettings.get_settings()
    return (
        f"Beleza! Pedido #{order.id} confirmado! 💳\n\n"
        f"Pagamento: *Cartão {card_name}*\n"
        f"⚠️ Taxa da maquininha: R$ 2,00\n\n"
        f"⏱️ Previsão: {settings_obj.min_delivery_time} a {settings_obj.max_delivery_time} min\n\n"
        f"Quando sair pra entrega eu te aviso aqui!\n\n"
        f"A Pizzaria do Negão agradece! ❤️"
    )


def handle_promo_request(phone: str) -> str:
    """Envia promocoes e cardapio em texto."""
    settings_obj = BusinessSettings.get_settings()

    response = "🔥 *PROMOÇÕES* 🔥\n\n"

    if settings_obj.promo_active and settings_obj.promo_text:
        response += "Hoje tá rolando: *2 Pizzas Grandes por R$ 55,00*\n"
        response += "(Delivery ou retirada — a taxa de entrega varia conforme o bairro.)\n\n"
    else:
        response += "No momento não temos promoções ativas 😕\n\n"

    # Cardápio de pizzas salgadas
    pizzas = Product.objects.filter(category='PIZZA', active=True).order_by('name')
    if pizzas:
        response += "*🍕 PIZZAS SALGADAS*\n"
        for i, pizza in enumerate(pizzas, 1):
            response += f"{i}. {pizza.name} - R$ {pizza.price:.2f}\n"
        response += "\n"

    # Cardápio de pizzas doces
    pizzas_doces = Product.objects.filter(category='PIZZA_DOCE', active=True)
    if pizzas_doces:
        response += "*🍫 PIZZAS DOCES*\n"
        for pizza in pizzas_doces:
            response += f"• {pizza.name} - R$ {pizza.price:.2f}\n"
        response += "\n"

    drinks = Product.objects.filter(category='BEBIDA', active=True)
    if drinks:
        response += "*🥤 BEBIDAS*\n"
        for drink in drinks:
            response += f"• {drink.name} - R$ {drink.price:.2f}\n"
        response += "\n"

    set_conversation_state(phone, "welcome", {})
    response += "E aí, o que vai ser hoje? 😋"
    return response


def handle_menu_request(phone: str) -> str:
    """Envia cardapio em texto."""
    menu = "Olha só nosso cardápio! 🍕\n\n"

    pizzas = Product.objects.filter(category='PIZZA', active=True).order_by('name')
    menu += "*🍕 PIZZAS SALGADAS*\n"
    for i, pizza in enumerate(pizzas, 1):
        menu += f"{i}. {pizza.name} - R$ {pizza.price:.2f}\n"

    # Pizzas doces
    pizzas_doces = Product.objects.filter(category='PIZZA_DOCE', active=True)
    if pizzas_doces:
        menu += "\n*🍫 PIZZAS DOCES*\n"
        for pizza in pizzas_doces:
            menu += f"• {pizza.name} - R$ {pizza.price:.2f}\n"

    drinks = Product.objects.filter(category='BEBIDA', active=True)
    if drinks:
        menu += "\n*🥤 BEBIDAS*\n"
        for drink in drinks:
            menu += f"• {drink.name} - R$ {drink.price:.2f}\n"

    menu += "\nE aí, o que vai ser hoje? 😋"

    set_conversation_state(phone, "welcome", {})
    return menu


def is_valid_phone(phone: str) -> bool:
    """Verifica se é um número de telefone válido (brasileiro ou internacional)."""
    if not phone:
        return False
    digits = ''.join(filter(str.isdigit, phone))
    # Aceita telefones com 8 a 15 dígitos (cobre maioria dos países)
    if len(digits) < 8 or len(digits) > 15:
        return False
    return True


def extract_phone_number(payload: dict) -> str:
    """Extrai o numero de telefone do payload do WAHA."""
    phone = None
    _data = payload.get('_data', {})
    info = _data.get('Info', {})

    # Lista de campos para tentar extrair o número (em ordem de prioridade)
    candidates = [
        payload.get('participant', ''),  # Em grupos, participant tem o número
        info.get('SenderAlt', ''),  # Formato: 556992690072:94@s.whatsapp.net
        info.get('Sender', ''),  # Formato: 556992690072:20@s.whatsapp.net
        payload.get('from', ''),  # Pode ser número ou LID
        payload.get('notifyName', ''),  # Às vezes contém info útil
    ]

    for candidate in candidates:
        if not candidate:
            continue

        # Ignora LIDs
        if '@lid' in candidate:
            continue

        # Extrai apenas a parte numérica antes de @ ou :
        phone = re.sub(r'[@:].*', '', candidate)

        # Remove não-dígitos
        if not phone.isdigit():
            phone = re.sub(r'\D', '', phone)

        # Valida se é um telefone válido (brasileiro ou internacional)
        if phone and is_valid_phone(phone):
            logger.info(f"Telefone extraido de '{candidate}': {phone}")
            return phone

    # Se não encontrou em nenhum campo, loga para debug
    from_field = payload.get('from', '')
    logger.warning(f"Nao foi possivel extrair telefone valido. from={from_field}, SenderAlt={info.get('SenderAlt')}, Sender={info.get('Sender')}")
    return None


@csrf_exempt
def bot_webhook(request):
    """Webhook principal para receber mensagens do WAHA."""
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    event = data.get('event')
    if event != 'message':
        return JsonResponse({"status": "ignored"})

    payload = data.get('payload', {})

    # DEBUG: Log do payload completo para identificar campos
    logger.info(f"DEBUG PAYLOAD: from={payload.get('from')} | participant={payload.get('participant')} | notifyName={payload.get('notifyName')}")
    logger.info(f"DEBUG _data: {payload.get('_data', {}).get('Info', {})}")

    # Verifica duplicação pelo ID da mensagem
    message_id = payload.get('id') or payload.get('_data', {}).get('Info', {}).get('ID', '')
    if is_message_duplicate(message_id):
        logger.info(f"Mensagem duplicada ignorada: {message_id}")
        return JsonResponse({"status": "duplicate"})

    if payload.get('fromMe', False):
        return JsonResponse({"status": "ignored"})

    # Extrai o número de telefone corretamente
    phone = extract_phone_number(payload)

    if not phone or len(phone) < 10:
        logger.warning(f"Numero de telefone invalido: {phone}")
        return JsonResponse({"status": "ignored", "reason": "invalid phone"})

    # Extrai informações da mensagem
    msg_type = payload.get('type', 'chat')
    body = payload.get('body', '')

    # Para imagens, o tipo pode ser 'image'
    if not msg_type:
        msg_type = 'chat'

    media_url = None
    if msg_type == 'image' or payload.get('hasMedia'):
        media = payload.get('media', {})
        media_url = media.get('url') if media else None

    # Extrai nome do cliente se disponível
    _data = payload.get('_data', {})
    info = _data.get('Info', {})
    push_name = info.get('PushName', '')

    if push_name:
        get_or_create_customer(phone, push_name)

    state = get_conversation_state(phone)
    current_state = state.get("state", "welcome")

    logger.info(f"Mensagem de {phone}: {body[:50]}... (estado: {current_state})")

    # Verifica comandos especiais primeiro
    if is_cancel_command(body):
        response = handle_cancel(phone)
        send_whatsapp_message(phone, response)
        return JsonResponse({"status": "ok"})

    if is_back_command(body):
        success, response = go_back_state(phone)
        send_whatsapp_message(phone, response)
        return JsonResponse({"status": "ok"})

    # Processa de acordo com o estado atual
    if current_state == "welcome":
        response = handle_welcome(phone, body, msg_type)

    elif current_state == "awaiting_pickup_items":
        response = handle_awaiting_items(phone, body, "PICKUP")

    elif current_state == "awaiting_promo_pizza_1":
        response = handle_promo_pizza_1(phone, body)

    elif current_state == "awaiting_promo_pizza_2":
        response = handle_promo_pizza_2(phone, body)

    elif current_state == "awaiting_promo_order_type":
        response = handle_promo_order_type(phone, body)

    elif current_state == "awaiting_half_half_first":
        response = handle_half_half_first(phone, body)

    elif current_state == "awaiting_half_half_second":
        response = handle_half_half_second(phone, body)

    elif current_state == "awaiting_observation":
        response = handle_observation(phone, body)

    elif current_state == "awaiting_more_items":
        response = handle_awaiting_more_items(phone, body)

    elif current_state == "awaiting_another_item":
        response = handle_awaiting_another_item(phone, body)

    elif current_state == "awaiting_more_items_pickup":
        response = handle_awaiting_more_items_pickup(phone, body)

    elif current_state == "awaiting_drink":
        response = handle_awaiting_drink(phone, body)

    elif current_state == "awaiting_drink_pickup":
        response = handle_awaiting_drink_pickup(phone, body)

    elif current_state == "awaiting_address":
        response = handle_awaiting_address(phone, body)

    elif current_state == "confirming_delivery":
        response = handle_confirming_delivery(phone, body)

    elif current_state == "confirming_pickup":
        response = handle_confirming_pickup(phone, body)

    elif current_state == "awaiting_receipt":
        response = handle_awaiting_receipt(phone, body, msg_type, media_url)

    elif current_state == "awaiting_payment_method":
        response = handle_payment_method(phone, body)

    elif current_state == "awaiting_change":
        response = handle_awaiting_change(phone, body)

    elif current_state == "awaiting_card_type":
        response = handle_card_type(phone, body)

    elif current_state == "awaiting_half_or_full":
        response = handle_half_or_full(phone, body)

    elif current_state == "awaiting_promo_half_or_full":
        response = handle_promo_half_or_full(phone, body)

    elif current_state == "awaiting_promo_second_after_half":
        response = handle_promo_second_after_half(phone, body)

    else:
        response = handle_welcome(phone, body, msg_type)

    if response:
        send_whatsapp_message(phone, response)

    return JsonResponse({"status": "ok"})


@csrf_exempt
def send_status_update(request):
    """Endpoint para enviar atualizacao de status manualmente."""
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    order_id = data.get('order_id')
    message = data.get('message')

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found"}, status=404)

    success = send_whatsapp_message(order.customer.phone, message)

    return JsonResponse({
        "status": "sent" if success else "failed",
        "phone": order.customer.phone
    })


def notify_out_for_delivery(order_id: int) -> bool:
    """Notifica cliente que pedido saiu para entrega."""
    try:
        order = Order.objects.get(id=order_id)
        settings_obj = BusinessSettings.get_settings()

        message = (
            "Boa noite, seu pedido esta a caminho! "
            "Ao chegar, nos notifique, por gentileza, se chegou tudo direitinho. "
            "E de suma importancia para o nosso crescimento com voces.\n"
            f"A {settings_obj.business_name} agradece pela preferencia!"
        )

        return send_whatsapp_message(order.customer.phone, message)
    except Order.DoesNotExist:
        return False


def notify_ready_for_pickup(order_id: int) -> bool:
    """Notifica cliente que pedido está pronto para retirada."""
    try:
        order = Order.objects.get(id=order_id)
        settings_obj = BusinessSettings.get_settings()

        message = (
            "Boa noite, seu pedido esta pronto para retirada!\n"
            f"A {settings_obj.business_name} agradece pela preferencia!"
        )

        return send_whatsapp_message(order.customer.phone, message)
    except Order.DoesNotExist:
        return False


@csrf_exempt
def debug_waha(request):
    """Endpoint de debug para testar conexao com WAHA."""
    from .waha_service import get_session_status, start_session, WAHA_URL, WAHA_SESSION

    if request.method == 'GET':
        # Retorna status da sessao
        status = get_session_status()
        return JsonResponse({
            "waha_url": WAHA_URL,
            "session": WAHA_SESSION,
            "session_status": status
        })

    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            data = {}

        action = data.get('action', 'test')

        if action == 'start':
            # Tenta iniciar sessao
            result = start_session()
            return JsonResponse({"action": "start_session", "result": result})

        elif action == 'test':
            # Testa envio de mensagem
            phone = data.get('phone', '')
            message = data.get('message', 'Teste de mensagem da Pizzaria do Negao!')

            if not phone:
                return JsonResponse({"error": "Informe o numero de telefone"}, status=400)

            success = send_whatsapp_message(phone, message)
            return JsonResponse({
                "action": "test_message",
                "phone": phone,
                "success": success
            })

    return JsonResponse({"error": "Metodo nao permitido"}, status=405)

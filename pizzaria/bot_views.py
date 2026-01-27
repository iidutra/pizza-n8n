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
        return False, "Voce esta no inicio. Nao ha como voltar."

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
        "awaiting_pickup_items": "Certo, voce vai retirar no local! Qual vai ser o pedido?",
        "awaiting_drink": get_drinks_menu(),
        "awaiting_drink_pickup": get_drinks_menu(),
        "awaiting_address": "Confirme o endereco completo, por gentileza.",
        "awaiting_receipt": "Por favor, mande o comprovante de pagamento.",
    }

    return True, state_messages.get(previous["state"], "Qual e o seu pedido para hoje?")


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
    return "Pedido cancelado. Se precisar de algo, e so chamar!"


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
    text = text.lower().strip()

    # Mapeamento de números/nomes para pizzas
    pizza_keywords = [
        ("1", "calabresa"), ("calabresa", "calabresa"),
        ("2", "frango"), ("frango", "frango"), ("catupiry", "frango"),
        ("3", "portuguesa"), ("portuguesa", "portuguesa"),
        ("4", "marguerita"), ("marguerita", "marguerita"),
        ("5", "queijos"), ("queijos", "queijos"), ("quatro", "queijos"),
        ("6", "bacon"), ("bacon", "bacon"),
        ("7", "pepperoni"), ("pepperoni", "pepperoni"),
        ("8", "mussarela"), ("mussarela", "mussarela"), ("mucarela", "mussarela"),
    ]

    for keyword, name in pizza_keywords:
        if keyword in text:
            product = Product.objects.filter(
                name__icontains=name,
                category='PIZZA',
                active=True
            ).first()
            if product:
                return product

    # Busca fuzzy
    products = Product.objects.filter(active=True, category='PIZZA')
    product_names = [(p.name.lower(), p) for p in products]

    if product_names:
        best_match = process.extractOne(
            text,
            [name for name, _ in product_names],
            scorer=fuzz.partial_ratio
        )
        if best_match and best_match[1] >= 60:
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
    menu = "Voce vai querer adicionar refrigerante?\n\n"

    for i, drink in enumerate(drinks, 1):
        menu += f"{i}. {drink.name} - R$ {drink.price:.2f}\n"

    menu += f"{len(drinks) + 1}. Nao, obrigado"
    return menu


def handle_welcome(phone: str, message: str, msg_type: str) -> str:
    """Trata estado inicial."""
    message_lower = message.lower()

    # Verifica se quer promoção/cardápio
    if any(word in message_lower for word in ['promo', 'promocao', 'promoção', 'oferta']):
        return handle_promo_request(phone)

    if any(word in message_lower for word in ['cardapio', 'cardápio', 'menu', 'catalogo']):
        return handle_menu_request(phone)

    # Verifica se quer retirada
    if any(word in message_lower for word in ['retirar', 'retirada', 'buscar', 'retira']):
        set_conversation_state(phone, "awaiting_pickup_items", {"order_type": "PICKUP"})
        return "Certo, voce vai retirar no local! Qual vai ser o pedido?"

    # Tenta encontrar um produto na mensagem
    product = find_product_fuzzy(message)
    if product:
        set_conversation_state(phone, "awaiting_drink", {
            "order_type": "DELIVERY",
            "items": [{"product_id": product.id, "quantity": 1}]
        })
        return get_drinks_menu()

    # Saudações - envia cardápio em texto
    greetings = ['oi', 'ola', 'olá', 'bom dia', 'boa tarde', 'boa noite', 'hey', 'eae', 'eai', 'opa']
    if any(greet in message_lower for greet in greetings):
        return send_welcome_with_menu(phone)

    # Mensagem de boas vindas padrão
    return "Boa noite, ja estamos atendendo. Qual e o seu pedido para hoje?"


def send_welcome_with_menu(phone: str) -> str:
    """Envia saudação com cardápio em texto."""
    settings_obj = BusinessSettings.get_settings()

    # Monta mensagem de boas vindas com promoção
    welcome = f"Boa noite! Bem-vindo a {settings_obj.business_name}!\n\n"

    # Adiciona promoção se ativa
    if settings_obj.promo_active and settings_obj.promo_text:
        welcome += f"*PROMOCAO:* {settings_obj.promo_text}\n\n"

    # Cardápio de pizzas
    pizzas = Product.objects.filter(category='PIZZA', active=True)
    if pizzas:
        welcome += "*CARDAPIO - PIZZAS*\n"
        for i, pizza in enumerate(pizzas, 1):
            welcome += f"{i}. {pizza.name} - R$ {pizza.price:.2f}\n"
        welcome += "\n"

    # Bebidas
    drinks = Product.objects.filter(category='BEBIDA', active=True)
    if drinks:
        welcome += "*BEBIDAS*\n"
        for drink in drinks:
            welcome += f"- {drink.name} - R$ {drink.price:.2f}\n"
        welcome += "\n"

    welcome += "Qual vai ser o pedido?"
    return welcome


def handle_awaiting_items(phone: str, message: str, order_type: str) -> str:
    """Trata selecao de itens para retirada."""
    product = find_product_fuzzy(message)
    if not product:
        return "Desculpe, nao encontrei esse produto. Pode repetir o pedido?"

    state = get_conversation_state(phone)
    items = state["data"].get("items", [])
    items.append({"product_id": product.id, "quantity": 1})

    set_conversation_state(phone, "awaiting_drink_pickup", {
        "items": items,
        "order_type": order_type
    })

    return get_drinks_menu()


def handle_awaiting_drink(phone: str, message: str) -> str:
    """Trata selecao de bebida para entrega."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])

    drinks = list(Product.objects.filter(category='BEBIDA', active=True)[:4])
    no_drink_option = str(len(drinks) + 1)

    # Verifica se não quer bebida
    if message_lower in [no_drink_option, "nao", "não", "n", "nao obrigado", "não obrigado"]:
        set_conversation_state(phone, "awaiting_address", {"items": items})
        return "Confirme o endereco completo, por gentileza."

    # Tenta encontrar a bebida
    drink = find_drink_by_option(message)
    if drink:
        items.append({"product_id": drink.id, "quantity": 1})

    set_conversation_state(phone, "awaiting_address", {"items": items})
    return "Confirme o endereco completo, por gentileza."


def handle_awaiting_drink_pickup(phone: str, message: str) -> str:
    """Trata selecao de bebida para retirada."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])

    drinks = list(Product.objects.filter(category='BEBIDA', active=True)[:4])
    no_drink_option = str(len(drinks) + 1)

    # Verifica se não quer bebida
    if message_lower not in [no_drink_option, "nao", "não", "n", "nao obrigado", "não obrigado"]:
        drink = find_drink_by_option(message)
        if drink:
            items.append({"product_id": drink.id, "quantity": 1})

    # Cria o pedido de retirada
    customer = get_or_create_customer(phone)

    order = Order.objects.create(
        customer=customer,
        order_type='PICKUP',
        status='PREPARING',
        payment_status='PAY_ON_DELIVERY'
    )

    for item_data in items:
        product = Product.objects.get(id=item_data["product_id"])
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=item_data["quantity"],
            unit_price=product.price
        )

    order.calculate_totals()
    order.save()

    clear_conversation_state(phone)

    return (
        "Muitissimo obrigada! \n"
        "Assim que seu pedido estiver pronto para retirada, lhe mandaremos uma mensagem."
    )


def handle_awaiting_address(phone: str, message: str) -> str:
    """Trata endereco de entrega."""
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])

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

    customer = get_or_create_customer(phone)
    customer.address = message
    customer.neighborhood = neighborhood
    customer.save()

    order = Order.objects.create(
        customer=customer,
        order_type='DELIVERY',
        delivery_address=message,
        neighborhood=neighborhood,
        delivery_fee=delivery_fee,
        status='AWAITING_PAYMENT'
    )

    for item_data in items:
        product = Product.objects.get(id=item_data["product_id"])
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=item_data["quantity"],
            unit_price=product.price
        )

    order.calculate_totals()
    order.save()

    set_conversation_state(phone, "awaiting_receipt", {"order_id": order.id})

    settings_obj = BusinessSettings.get_settings()

    response = f"A chave Pix e {settings_obj.pix_key} - {settings_obj.pix_name}.\n"
    response += "Por favor, mande o comprovante. "
    response += f"Seu pedido esta em andamento e o prazo de entrega e de {settings_obj.min_delivery_time} a {settings_obj.max_delivery_time} min.\n"
    response += f"A {settings_obj.business_name} agradece a preferencia!"

    return response


def handle_awaiting_receipt(phone: str, message: str, msg_type: str, media_url: str = None) -> str:
    """Trata recebimento do comprovante."""
    state = get_conversation_state(phone)
    order_id = state["data"].get("order_id")

    if not order_id:
        clear_conversation_state(phone)
        return "Desculpe, houve um erro. Por favor, faca um novo pedido."

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        clear_conversation_state(phone)
        return "Pedido nao encontrado. Por favor, faca um novo pedido."

    # Aceita qualquer mensagem como confirmação do comprovante (texto ou imagem)
    if msg_type == 'image' or media_url or message:
        if msg_type == 'image' and media_url:
            try:
                headers = {'X-Api-Key': settings.WAHA_API_KEY} if hasattr(settings, 'WAHA_API_KEY') else {}
                response = requests.get(media_url, headers=headers, timeout=30)
                if response.status_code == 200:
                    filename = f"receipt_{order.id}.jpg"
                    order.payment_receipt.save(filename, ContentFile(response.content))
            except Exception as e:
                logger.error(f"Erro ao baixar comprovante: {e}")

        order.payment_status = 'RECEIPT_RECEIVED'
        order.status = 'PREPARING'
        order.save()

        clear_conversation_state(phone)

        settings_obj = BusinessSettings.get_settings()
        return (
            f"Certo, seu pedido esta em andamento. "
            f"O prazo para a entrega sera de {settings_obj.min_delivery_time} a {settings_obj.max_delivery_time} min. "
            f"Assim que seu pedido sair para entrega, lhe mandaremos uma mensagem.\n"
            f"A {settings_obj.business_name} agradece a preferencia."
        )

    return "Por favor, envie o comprovante de pagamento (imagem)."


def handle_promo_request(phone: str) -> str:
    """Envia promocoes e cardapio em texto."""
    settings_obj = BusinessSettings.get_settings()

    response = ""

    # Promoção
    if settings_obj.promo_active and settings_obj.promo_text:
        response += f"*PROMOCAO*\n{settings_obj.promo_text}\n\n"
    else:
        response += "No momento nao temos promocoes ativas.\n\n"

    # Cardápio
    pizzas = Product.objects.filter(category='PIZZA', active=True)
    if pizzas:
        response += "*CARDAPIO - PIZZAS*\n"
        for i, pizza in enumerate(pizzas, 1):
            response += f"{i}. {pizza.name} - R$ {pizza.price:.2f}\n"
        response += "\n"

    drinks = Product.objects.filter(category='BEBIDA', active=True)
    if drinks:
        response += "*BEBIDAS*\n"
        for drink in drinks:
            response += f"- {drink.name} - R$ {drink.price:.2f}\n"
        response += "\n"

    set_conversation_state(phone, "welcome", {})
    response += "Qual vai ser o pedido?"
    return response


def handle_menu_request(phone: str) -> str:
    """Envia cardapio em texto."""
    pizzas = Product.objects.filter(category='PIZZA', active=True)
    menu = "*CARDAPIO - PIZZAS*\n"
    for i, pizza in enumerate(pizzas, 1):
        menu += f"{i}. {pizza.name} - R$ {pizza.price:.2f}\n"

    drinks = Product.objects.filter(category='BEBIDA', active=True)
    menu += "\n*BEBIDAS*\n"
    for drink in drinks:
        menu += f"- {drink.name} - R$ {drink.price:.2f}\n"

    set_conversation_state(phone, "welcome", {})
    return menu + "\nQual vai ser o pedido?"


def extract_phone_number(payload: dict) -> str:
    """Extrai o numero de telefone do payload do WAHA."""
    # Tenta extrair do _data.Info.SenderAlt (formato: 556992690072:94@s.whatsapp.net)
    _data = payload.get('_data', {})
    info = _data.get('Info', {})
    sender_alt = info.get('SenderAlt', '')

    if sender_alt:
        # Remove o sufixo :XX@s.whatsapp.net
        phone = re.sub(r':\d+@.*', '', sender_alt)
        if phone and phone.isdigit():
            return phone

    # Tenta do campo from
    from_field = payload.get('from', '')

    # Se o from termina com @c.us ou @s.whatsapp.net, é um número válido
    if '@c.us' in from_field or '@s.whatsapp.net' in from_field:
        phone = re.sub(r'[@:].*', '', from_field)
        if phone and phone.isdigit() and len(phone) >= 10:
            return phone

    # Remove sufixos conhecidos
    phone = from_field.replace('@c.us', '').replace('@s.whatsapp.net', '').replace('@lid', '')

    # Remove :XX se houver (formato 556992690072:94)
    phone = re.sub(r':\d+$', '', phone)

    # Se ainda não for um número válido, tenta extrair apenas dígitos
    if not phone.isdigit():
        digits = re.sub(r'\D', '', phone)
        if len(digits) >= 10:
            phone = digits

    return phone


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

    elif current_state == "awaiting_drink":
        response = handle_awaiting_drink(phone, body)

    elif current_state == "awaiting_drink_pickup":
        response = handle_awaiting_drink_pickup(phone, body)

    elif current_state == "awaiting_address":
        response = handle_awaiting_address(phone, body)

    elif current_state == "awaiting_receipt":
        response = handle_awaiting_receipt(phone, body, msg_type, media_url)

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

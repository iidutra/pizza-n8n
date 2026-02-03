import json
import logging
import re
import time
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

# Período de graça após iniciar o serviço - ignora TODAS as mensagens por 60 segundos
# Isso evita disparo em massa quando o WAHA sincroniza após deploy
SERVICE_START_TIME = time.time()
STARTUP_GRACE_PERIOD = 60  # segundos

# Endereço para retirada
PICKUP_ADDRESS = "Rua Eudoxia de Barros, 6219 - Aponiã"
PICKUP_MAPS_LINK = "https://www.google.com/maps/search/?api=1&query=Rua+Eudoxia+de+Barros+6219+Aponia+Porto+Velho"

# Telefone para contato (quando cliente manda áudio)
CONTACT_PHONE = "(69) 99363-9552"


def get_help_text() -> str:
    """Retorna texto de ajuda com comandos disponíveis."""
    return "\n\n_Comandos: 'voltar' (etapa anterior) | 'cancelar' (desistir do pedido)_"


def format_order_summary(items: list, delivery_fee: Decimal = None, order_type: str = 'DELIVERY', is_promo: bool = False, customer_name: str = None, customer_phone: str = None) -> str:
    """Formata resumo do pedido."""
    summary = "*RESUMO DO PEDIDO*\n"

    # Adiciona dados do cliente se fornecidos
    if customer_name or customer_phone:
        summary += "━━━━━━━━━━━━━━━━━━━━\n"
        if customer_name:
            summary += f"👤 *Cliente:* {customer_name}\n"
        if customer_phone:
            # Formata telefone para exibição
            phone_display = customer_phone
            if phone_display.startswith("55") and len(phone_display) >= 12:
                phone_display = f"({phone_display[2:4]}) {phone_display[4:9]}-{phone_display[9:]}"
            summary += f"📱 *Telefone:* {phone_display}\n"
        summary += "━━━━━━━━━━━━━━━━━━━━\n"

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


# ============================================
# DETECÇÃO DE CONVERSAS HUMANIZADAS
# ============================================

def is_greeting(text: str) -> bool:
    """Detecta saudações no meio do fluxo."""
    text_lower = text.lower().strip()
    greetings = [
        'oi', 'olá', 'ola', 'oie', 'oii', 'oiii',
        'bom dia', 'boa tarde', 'boa noite',
        'eai', 'eae', 'e ai', 'e aí',
        'opa', 'fala', 'salve',
        'tudo bem', 'tudo bom', 'como vai', 'como você está',
        'beleza', 'blz', 'td bem'
    ]
    return any(text_lower == g or text_lower.startswith(g + ' ') or text_lower.startswith(g + ',') for g in greetings)


def is_question(text: str) -> tuple:
    """
    Detecta perguntas comuns e retorna (is_question, question_type, response).
    question_type: 'price', 'time', 'have', 'general', None
    """
    text_lower = text.lower().strip()

    # Perguntas sobre preço
    price_patterns = [
        'quanto custa', 'quanto é', 'qual o preço', 'qual é o preço',
        'qual o valor', 'quanto fica', 'quanto sai', 'preço da', 'valor da'
    ]
    if any(p in text_lower for p in price_patterns):
        return True, 'price', "Os preços variam de R$ 35 a R$ 45 por pizza. Quer ver o cardápio completo? Digite *cardápio*"

    # Perguntas sobre tempo/entrega
    time_patterns = [
        'quanto tempo', 'demora quanto', 'prazo de entrega', 'tempo de entrega',
        'quanto demora', 'chega em quanto', 'entrega em quanto'
    ]
    if any(p in text_lower for p in time_patterns):
        return True, 'time', "O tempo de entrega é de 50 a 70 minutos, dependendo do bairro. Vamos continuar seu pedido?"

    # Perguntas sobre disponibilidade
    have_patterns = [
        'vocês tem', 'vocês têm', 'vcs tem', 'tem pizza de', 'tem sabor',
        'ainda tem', 'disponível', 'acabou'
    ]
    if any(p in text_lower for p in have_patterns):
        return True, 'have', "Temos várias opções! Digite *cardápio* para ver todos os sabores disponíveis."

    # Perguntas sobre funcionamento
    open_patterns = [
        'tá aberto', 'está aberto', 'funciona', 'abre que horas', 'fecha que horas',
        'horário de funcionamento', 'vocês abrem', 'vocês fecham'
    ]
    if any(p in text_lower for p in open_patterns):
        return True, 'hours', "Funcionamos das 19h às 23h. Estamos abertos agora! Posso anotar seu pedido?"

    # Perguntas sobre formas de pagamento
    payment_patterns = [
        'aceita pix', 'aceita cartão', 'aceita cartao', 'aceita dinheiro',
        'formas de pagamento', 'como paga', 'como posso pagar'
    ]
    if any(p in text_lower for p in payment_patterns):
        return True, 'payment', "Aceitamos PIX, cartão (crédito/débito) e dinheiro. Vamos continuar seu pedido?"

    # Perguntas genéricas com "?"
    if '?' in text_lower and len(text_lower) > 5:
        return True, 'general', None

    return False, None, None


def is_change_of_mind(text: str) -> tuple:
    """Detecta quando cliente quer mudar de ideia."""
    text_lower = text.lower().strip()

    # Quer mudar para retirada
    if any(p in text_lower for p in ['quero retirar', 'vou buscar', 'retirada', 'quero retirada', 'vou retirar']):
        return True, 'pickup'

    # Quer mudar para entrega
    if any(p in text_lower for p in ['quero entrega', 'entrega por favor', 'pode entregar']):
        return True, 'delivery'

    # Quer mudar o pedido
    if any(p in text_lower for p in ['quero trocar', 'quero mudar', 'na verdade', 'espera', 'peraí', 'mudei de ideia']):
        return True, 'change'

    # Quer ver o pedido atual
    if any(p in text_lower for p in ['meu pedido', 'o que eu pedi', 'resumo', 'total até agora']):
        return True, 'summary'

    return False, None


def get_context_help(state: str) -> str:
    """Retorna ajuda contextual baseada no estado atual."""
    help_messages = {
        'awaiting_promo_pizza_1': "Você está escolhendo a *primeira pizza* da promoção.\n\nDigite o número ou nome do sabor, ou 'voltar' para cancelar.",
        'awaiting_promo_pizza_2': "Você está escolhendo a *segunda pizza* da promoção.\n\nDigite o número ou nome do sabor, ou 'voltar'.",
        'awaiting_half_half_first': "Você está montando uma pizza *meio a meio*.\n\nDigite o primeiro sabor, ou 'voltar'.",
        'awaiting_half_half_second': "Você está escolhendo o *segundo sabor* da meio a meio.\n\nDigite o sabor, ou 'voltar'.",
        'awaiting_more_items': "Você pode adicionar mais pizzas ou finalizar.\n\n1️⃣ Quero mais\n2️⃣ Só isso",
        'awaiting_address': "Preciso do *endereço completo* para entrega.\n\nEx: Rua das Flores, 123, Centro",
        'awaiting_payment': "Escolha a *forma de pagamento*:\n\n1️⃣ PIX\n2️⃣ Cartão\n3️⃣ Dinheiro",
        'awaiting_observation': "Alguma *observação* no pedido?\n\nDigite a observação ou 'não' se não tiver.",
    }
    return help_messages.get(state, "Digite 'cardápio' para ver opções ou 'cancelar' para recomeçar.")


def handle_humanized_input(phone: str, text: str, current_state: str) -> str:
    """
    Trata inputs humanizados (perguntas, saudações, mudança de ideia).
    Retorna uma resposta se detectou algo, ou None para continuar fluxo normal.
    """
    # Detecta saudação no meio do fluxo
    if is_greeting(text) and current_state not in ['welcome', 'greeting']:
        help_text = get_context_help(current_state)
        return f"Oi! 👋 Estamos no meio do seu pedido.\n\n{help_text}"

    # Detecta perguntas
    is_q, q_type, response = is_question(text)
    if is_q and response:
        return response
    if is_q and q_type == 'general':
        help_text = get_context_help(current_state)
        return f"Não entendi sua pergunta 😅\n\n{help_text}\n\nOu digite 'ajuda' para mais opções."

    # Detecta mudança de ideia
    changed, change_type = is_change_of_mind(text)
    if changed:
        if change_type == 'summary':
            state = get_conversation_state(phone)
            items = state.get('data', {}).get('items', [])
            if items:
                return format_order_summary(items, state.get('data', {}).get('order_type', 'DELIVERY'))
            return "Você ainda não adicionou nenhum item ao pedido."
        if change_type == 'change':
            return "Sem problemas! Digite 'voltar' para voltar ao passo anterior, ou 'cancelar' para recomeçar."

    return None


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
        "awaiting_payment_choice": "Como vai ser o pagamento?\n1. PIX\n2. Dinheiro\n3. Cartão Crédito\n4. Cartão Débito",
        "awaiting_receipt": "Aguardando comprovante de pagamento (foto).",
        "awaiting_payment_method": "Como vai ser o pagamento na entrega?\n1. Dinheiro\n2. Cartão (taxa de R$ 2,00)",
        "awaiting_change": "Vai precisar de troco? Se sim, pra quanto?",
        "awaiting_card_type": "Cartão: vai ser crédito ou débito?\n1. Crédito\n2. Débito",
        "awaiting_half_or_full": "Como você quer?\n1. Meio a meio\n2. Duas pizzas inteiras",
        "awaiting_promo_half_or_full": "Promoção - como você quer?\n1. Meio a meio\n2. Duas pizzas inteiras",
        "awaiting_promo_second_after_half": "Promoção meio a meio! Qual o segundo sabor?",
        "awaiting_more_promo": "Quer mais uma promoção?\n1. Sim, quero mais 2 pizzas por R$ 55\n2. Não, só isso",
        "awaiting_promo_more_items": "Quer adicionar mais pizza?\n1. Mais promoção (2 por R$55)\n2. Pizza avulsa\n3. Não, só isso",
        "awaiting_promo_another_item": "Qual pizza você quer adicionar?",
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


def extract_observation(text: str) -> tuple:
    """
    Extrai observações de remoção/adição do texto do pedido.
    Retorna (texto_limpo, observacao).
    Ex: "calabresa sem cebola" -> ("calabresa", "sem cebola")
    """
    text_lower = text.lower().strip()
    observations = []

    # Padrões de remoção: "sem X", "tirar X", "não quero X", "retira X"
    remove_patterns = [
        r'sem\s+([a-záéíóúàâêôãõç\s]+?)(?:\s*,|\s+e\s+|\s*$)',
        r'tirar?\s+(?:a\s+|o\s+)?([a-záéíóúàâêôãõç\s]+?)(?:\s*,|\s+e\s+|\s*$)',
        r'não\s+quero\s+([a-záéíóúàâêôãõç\s]+?)(?:\s*,|\s+e\s+|\s*$)',
        r'retira(?:r)?\s+(?:a\s+|o\s+)?([a-záéíóúàâêôãõç\s]+?)(?:\s*,|\s+e\s+|\s*$)',
        r'por\s+favor\s+sem\s+([a-záéíóúàâêôãõç\s]+?)(?:\s*,|\s+e\s+|\s*$)',
    ]

    clean_text = text_lower

    for pattern in remove_patterns:
        matches = re.findall(pattern, clean_text)
        for match in matches:
            ingredient = match.strip()
            if ingredient and len(ingredient) >= 3:
                observations.append(f"sem {ingredient}")
                # Remove do texto original
                clean_text = re.sub(pattern, ' ', clean_text)

    # Padrões de adição: "com extra X", "adicionar X"
    add_patterns = [
        r'(?:com\s+)?extra\s+([a-záéíóúàâêôãõç\s]+?)(?:\s*,|\s+e\s+|\s*$)',
        r'adicionar?\s+([a-záéíóúàâêôãõç\s]+?)(?:\s*,|\s+e\s+|\s*$)',
    ]

    for pattern in add_patterns:
        matches = re.findall(pattern, clean_text)
        for match in matches:
            ingredient = match.strip()
            if ingredient and len(ingredient) >= 3:
                observations.append(f"com extra {ingredient}")
                clean_text = re.sub(pattern, ' ', clean_text)

    # Limpa o texto
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()

    observation = ', '.join(observations) if observations else None
    return clean_text, observation


def find_product_with_observation(text: str) -> tuple:
    """
    Encontra produto e extrai observação.
    Retorna (Product, observation_string).
    """
    clean_text, observation = extract_observation(text)
    product = find_product_fuzzy(clean_text)
    return product, observation


def find_product_fuzzy(text: str) -> Product:
    """Encontra produto por correspondencia fuzzy."""
    original_text = text
    text = text.lower().strip()
    logger.info(f"DEBUG find_product_fuzzy: original={repr(original_text)}, after_strip={repr(text)}, isdigit={text.isdigit()}")

    # Se é um número, busca direto pelo índice do cardápio (só pizzas salgadas)
    if text.isdigit():
        idx = int(text)
        pizzas = list(Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True).order_by('category', 'name'))
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
    drinks = list(Product.objects.filter(category='BEBIDA', active=True).order_by('name'))

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

    # Ignora palavras muito curtas (menos de 4 caracteres)
    if len(neighborhood) < 4:
        return None

    # Busca exata primeiro
    exact = DeliveryFee.objects.filter(
        neighborhood__iexact=neighborhood,
        active=True
    ).first()
    if exact:
        return exact

    # Busca se o nome do bairro contém a palavra (ou vice-versa)
    fees = DeliveryFee.objects.filter(active=True)
    for fee in fees:
        fee_name = fee.neighborhood.lower()
        # Verifica se um contém o outro (mínimo 4 caracteres)
        if len(neighborhood) >= 4 and (neighborhood in fee_name or fee_name in neighborhood):
            return fee

    # Busca fuzzy apenas com threshold alto (85%) e ratio completo
    fee_names = [(f.neighborhood.lower(), f) for f in fees]
    if fee_names:
        best_match = process.extractOne(
            neighborhood,
            [name for name, _ in fee_names],
            scorer=fuzz.ratio  # Usa ratio completo, não partial
        )
        # Threshold alto de 85% para evitar falsos positivos
        if best_match and best_match[1] >= 85:
            for name, fee in fee_names:
                if name == best_match[0]:
                    return fee

    return None


def get_drinks_menu() -> str:
    """Retorna menu de bebidas formatado."""
    drinks = Product.objects.filter(category='BEBIDA', active=True).order_by('name')
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
        pizzas = list(Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True).order_by('category', 'name'))
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


def parse_two_pizza_names(text: str) -> tuple:
    """Detecta quando usuário digita dois nomes de pizza. Ex: '4 queijos e calabresa', 'portuguesa e frango'"""
    text_lower = text.lower().strip()

    # Remove prefixos comuns
    text_lower = re.sub(r'^(quero|uma|pizza|a)\s+', '', text_lower)
    text_lower = re.sub(r'\s+(quero|uma|pizza)\s+', ' ', text_lower)

    # Detecta padrão "X metade Y e Z metade W" (duas pizzas meio a meio)
    # Ex: "baiana metade 4 queijos e portuguesa metade palmito"
    match_double_half = re.search(
        r'(\w+(?:\s+\w+)?)\s+(?:metade|meia|meio)\s+(\w+(?:\s+\w+)?)\s+e\s+(?:uma\s+)?(\w+(?:\s+\w+)?)\s+(?:metade|meia|meio)\s+(\w+(?:\s+\w+)?)',
        text_lower
    )
    if match_double_half:
        # Retorna apenas as duas primeiras pizzas (para primeira seleção da promo)
        pizza1 = find_product_fuzzy(match_double_half.group(1))
        pizza2 = find_product_fuzzy(match_double_half.group(2))
        if pizza1 and pizza2:
            return pizza1, pizza2

    # Detecta padrão "X metade Y" (uma pizza meio a meio)
    match_half = re.search(r'(\w+(?:\s+\w+)?)\s+(?:metade|meia|meio)\s+(\w+(?:\s+\w+)?)', text_lower)
    if match_half:
        pizza1 = find_product_fuzzy(match_half.group(1))
        pizza2 = find_product_fuzzy(match_half.group(2))
        if pizza1 and pizza2:
            return pizza1, pizza2

    # Separadores possíveis: " e ", " com ", " + "
    separators = [' e ', ' com ', ' + ', ', ']

    for sep in separators:
        if sep in text_lower:
            parts = text_lower.split(sep, 1)  # Divide apenas na primeira ocorrência
            if len(parts) == 2:
                part1 = parts[0].strip()
                part2 = parts[1].strip()

                # Remove "metade", "meia", etc que sobrou
                part1 = re.sub(r'\s*(metade|meia|meio)\s*$', '', part1)
                part2 = re.sub(r'^\s*(metade|meia|meio)\s*', '', part2)

                # Tenta encontrar cada parte como pizza
                if part1 and part2:
                    pizza1 = find_product_fuzzy(part1)
                    pizza2 = find_product_fuzzy(part2)

                    if pizza1 and pizza2:
                        return pizza1, pizza2

    return None


def handle_half_or_full(phone: str, message: str) -> str:
    """Trata escolha entre meio a meio ou duas pizzas inteiras."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    pizza1_id = state["data"].get("pizza1_id")
    pizza2_id = state["data"].get("pizza2_id")
    pizza1_name = state["data"].get("pizza1_name")
    pizza2_name = state["data"].get("pizza2_name")

    # Observações já salvas anteriormente
    obs1 = state["data"].get("pizza1_obs", "")
    obs2 = state["data"].get("pizza2_obs", "")

    try:
        pizza1 = Product.objects.get(id=pizza1_id)
        pizza2 = Product.objects.get(id=pizza2_id)
    except Product.DoesNotExist:
        clear_conversation_state(phone)
        return "Ops, algo deu errado 😅 Vamos recomeçar!"

    # Detecta se é uma observação (ex: "calabresa sem cebola", "sem cebola na calabresa")
    obs_patterns = ['sem ', 'tirar ', 'com extra ', 'adicionar ', 'sem a ', 'tira ']
    has_observation = any(p in message_lower for p in obs_patterns)

    if has_observation:
        # Tenta identificar qual pizza a observação se refere
        pizza1_lower = pizza1.name.lower()
        pizza2_lower = pizza2.name.lower()

        # Extrai a observação
        _, observation = extract_observation(message)
        if not observation:
            observation = message_lower

        # Verifica se menciona qual pizza
        if pizza1_lower in message_lower or any(word in message_lower for word in pizza1_lower.split()):
            obs1 = observation
            pizza_ref = pizza1.name
        elif pizza2_lower in message_lower or any(word in message_lower for word in pizza2_lower.split()):
            obs2 = observation
            pizza_ref = pizza2.name
        else:
            # Não identificou qual pizza, assume a primeira
            obs1 = observation
            pizza_ref = pizza1.name

        # Salva observação no estado e pergunta novamente
        set_conversation_state(phone, "awaiting_half_or_full", {
            **state["data"],
            "pizza1_obs": obs1,
            "pizza2_obs": obs2
        })

        obs_list = []
        if obs1:
            obs_list.append(f"• {pizza1.name}: _{obs1}_")
        if obs2:
            obs_list.append(f"• {pizza2.name}: _{obs2}_")
        obs_text = "\n".join(obs_list)

        return (
            f"Anotei! ✅ *{pizza_ref}*: _{observation}_\n\n"
            f"📝 *Observações:*\n{obs_text}\n\n"
            f"Agora escolhe como quer:\n"
            f"1️⃣ Meio a meio (uma pizza com metade de cada + uma inteira)\n"
            f"2️⃣ Duas pizzas inteiras (uma de cada sabor)\n\n"
            f"_'voltar' | 'cancelar'_"
        )

    # Meio a meio
    if message_lower in ['1', 'meio', 'metade', 'meio a meio', 'meia']:
        preco = max(pizza1.price, pizza2.price)
        obs_combined = []
        if obs1:
            obs_combined.append(f"{pizza1.name}: {obs1}")
        if obs2:
            obs_combined.append(f"{pizza2.name}: {obs2}")
        observation = " | ".join(obs_combined) if obs_combined else None

        set_conversation_state(phone, "awaiting_observation", {
            "order_type": "DELIVERY",
            "current_item": {
                "type": "half_half",
                "pizza1_id": pizza1.id,
                "pizza2_id": pizza2.id,
                "pizza1_name": pizza1.name,
                "pizza2_name": pizza2.name,
                "price": float(preco),
                "observation": observation
            },
            "items": []
        })

        obs_msg = f"\n📝 _{observation}_" if observation else ""
        return (
            f"Boa! 🍕 *Meio a Meio:*\n"
            f"½ {pizza1.name} + ½ {pizza2.name}\n"
            f"💰 R$ {preco:.2f}{obs_msg}\n\n"
            f"Mais alguma observação? (tirar cebola, sem tomate, etc)\n\n"
            f"_Digite a observação ou 'não' se não tiver_"
        )

    # Duas pizzas inteiras
    if message_lower in ['2', 'duas', 'inteira', 'inteiras', 'separadas', 'separado']:
        items = [
            {"type": "single", "product_id": pizza1.id, "quantity": 1, "price": float(pizza1.price), "observation": obs1 or None},
            {"type": "single", "product_id": pizza2.id, "quantity": 1, "price": float(pizza2.price), "observation": obs2 or None}
        ]
        total = pizza1.price + pizza2.price
        set_conversation_state(phone, "awaiting_more_items", {
            "order_type": "DELIVERY",
            "items": items
        })

        obs1_text = f" _{obs1}_" if obs1 else ""
        obs2_text = f" _{obs2}_" if obs2 else ""
        return (
            f"Anotado! ✅\n\n"
            f"• 1x *{pizza1.name}* - R$ {pizza1.price:.2f}{obs1_text}\n"
            f"• 1x *{pizza2.name}* - R$ {pizza2.price:.2f}{obs2_text}\n"
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
        pizzas = list(Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True).order_by('category', 'name'))
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

    # Tenta encontrar um produto na mensagem (com possível observação)
    product, observation = find_product_with_observation(message)
    if product:
        current_item = {
            "type": "single",
            "product_id": product.id,
            "price": float(product.price)
        }

        # Se já extraiu observação, inclui e pula etapa
        if observation:
            current_item["observation"] = observation
            set_conversation_state(phone, "awaiting_more_items", {
                "items": [current_item],
                "order_type": "DELIVERY"
            })
            obs_text = f"\n📝 _{observation}_"
            return (
                f"Boa escolha! 😋 *{product.name}* - R$ {product.price:.2f}{obs_text}\n\n"
                f"Mais alguma pizza?\n"
                f"1️⃣ Quero mais\n"
                f"2️⃣ Só isso"
            )

        set_conversation_state(phone, "awaiting_observation", {
            "order_type": "DELIVERY",
            "current_item": current_item,
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
        pizza1, obs1 = find_product_with_observation(sabor1_text)
        pizza2, obs2 = find_product_with_observation(sabor2_text)

        if pizza1 and pizza2:
            # Preço da meio a meio: maior preço entre as duas
            preco = max(pizza1.price, pizza2.price)

            # Combina observações das duas metades
            combined_obs = []
            if obs1:
                combined_obs.append(f"½ {pizza1.name}: {obs1}")
            if obs2:
                combined_obs.append(f"½ {pizza2.name}: {obs2}")
            final_observation = "; ".join(combined_obs) if combined_obs else None

            current_item = {
                "type": "half_half",
                "pizza1_id": pizza1.id,
                "pizza2_id": pizza2.id,
                "pizza1_name": pizza1.name,
                "pizza2_name": pizza2.name,
                "price": float(preco)
            }

            # Se já tem observação, pula a etapa
            if final_observation:
                current_item["observation"] = final_observation
                set_conversation_state(phone, "awaiting_more_items", {
                    "items": [current_item],
                    "order_type": "DELIVERY"
                })
                return (
                    f"Boa! 🍕 *Meio a Meio:*\n"
                    f"½ {pizza1.name} + ½ {pizza2.name}\n"
                    f"💰 R$ {preco:.2f}\n"
                    f"📝 _{final_observation}_\n\n"
                    f"Mais alguma pizza?\n"
                    f"1️⃣ Quero mais\n"
                    f"2️⃣ Só isso"
                )

            set_conversation_state(phone, "awaiting_observation", {
                "order_type": "DELIVERY",
                "current_item": current_item,
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
                "pizza1_name": pizza1.name,
                "pizza1_obs": obs1
            })
            return f"Beleza! Meia *{pizza1.name}*. E a outra metade, qual sabor?"
        elif pizza2:
            # Encontrou só a segunda, pede a primeira
            set_conversation_state(phone, "awaiting_half_half_first", {
                "pizza2_id": pizza2.id,
                "pizza2_name": pizza2.name,
                "pizza2_obs": obs2
            })
            return f"Beleza! Meia *{pizza2.name}*. E a outra metade, qual sabor?"

    # Não conseguiu identificar, inicia fluxo meio a meio
    set_conversation_state(phone, "awaiting_half_half_first", {})

    pizzas = Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True).order_by('category', 'name')
    menu = "Pizza meio a meio! 🍕\n\nEscolhe o *primeiro* sabor:\n\n"
    for i, pizza in enumerate(pizzas, 1):
        menu += f"{i}. {pizza.name}\n"
    menu += "\n_Digite o número ou nome | 'voltar' | 'sair'_"
    return menu


def handle_half_half_first(phone: str, message: str) -> str:
    """Trata seleção do primeiro sabor da meio a meio."""
    # Verifica inputs humanizados
    humanized_response = handle_humanized_input(phone, message, "awaiting_half_half_first")
    if humanized_response:
        return humanized_response

    state = get_conversation_state(phone)
    pizza2_id = state["data"].get("pizza2_id")
    pizza2_name = state["data"].get("pizza2_name")
    pizza2_obs = state["data"].get("pizza2_obs")

    product, observation = find_product_with_observation(message)
    if not product:
        return "Hmm, não achei esse sabor 🤔\n\nDigite o *número* ou *nome* do sabor.\nEx: '1' ou 'calabresa'\n\n_'voltar' | 'sair'_"

    if pizza2_id:
        # Já tem o segundo sabor, finaliza
        try:
            pizza2 = Product.objects.get(id=pizza2_id)
            preco = max(product.price, pizza2.price)

            # Combina observações das duas metades
            combined_obs = []
            if observation:
                combined_obs.append(f"½ {product.name}: {observation}")
            if pizza2_obs:
                combined_obs.append(f"½ {pizza2.name}: {pizza2_obs}")
            final_observation = "; ".join(combined_obs) if combined_obs else None

            current_item = {
                "type": "half_half",
                "pizza1_id": product.id,
                "pizza2_id": pizza2.id,
                "pizza1_name": product.name,
                "pizza2_name": pizza2.name,
                "price": float(preco)
            }

            # Se já tem observação, pula a etapa
            if final_observation:
                current_item["observation"] = final_observation
                set_conversation_state(phone, "awaiting_more_items", {
                    "items": [current_item],
                    "order_type": "DELIVERY"
                })
                return (
                    f"Boa! 🍕 *Meio a Meio:*\n"
                    f"½ {product.name} + ½ {pizza2.name}\n"
                    f"💰 R$ {preco:.2f}\n"
                    f"📝 _{final_observation}_\n\n"
                    f"Mais alguma pizza?\n"
                    f"1️⃣ Quero mais\n"
                    f"2️⃣ Só isso"
                )

            set_conversation_state(phone, "awaiting_observation", {
                "order_type": "DELIVERY",
                "current_item": current_item,
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
        "pizza1_name": product.name,
        "pizza1_obs": observation
    })

    pizzas = Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True).order_by('category', 'name')
    menu = f"Boa! ½ *{product.name}* ✅\n\nAgora o *segundo* sabor:\n\n"
    for i, pizza in enumerate(pizzas, 1):
        menu += f"{i}. {pizza.name}\n"
    menu += "\n_Digite o número ou nome | 'voltar' | 'sair'_"
    return menu


def handle_half_half_second(phone: str, message: str) -> str:
    """Trata seleção do segundo sabor da meio a meio."""
    # Verifica inputs humanizados
    humanized_response = handle_humanized_input(phone, message, "awaiting_half_half_second")
    if humanized_response:
        return humanized_response

    state = get_conversation_state(phone)
    pizza1_id = state["data"].get("pizza1_id")
    pizza1_name = state["data"].get("pizza1_name")
    pizza1_obs = state["data"].get("pizza1_obs")

    product, observation = find_product_with_observation(message)
    if not product:
        return "Hmm, não achei esse sabor 🤔\n\nDigite o *número* ou *nome* do segundo sabor.\n\n_'voltar' | 'sair'_"

    try:
        pizza1 = Product.objects.get(id=pizza1_id)
        preco = max(pizza1.price, product.price)

        # Combina observações das duas metades
        combined_obs = []
        if pizza1_obs:
            combined_obs.append(f"½ {pizza1.name}: {pizza1_obs}")
        if observation:
            combined_obs.append(f"½ {product.name}: {observation}")
        final_observation = "; ".join(combined_obs) if combined_obs else None

        current_item = {
            "type": "half_half",
            "pizza1_id": pizza1.id,
            "pizza2_id": product.id,
            "pizza1_name": pizza1.name,
            "pizza2_name": product.name,
            "price": float(preco)
        }

        # Se já tem observação, pula a etapa
        if final_observation:
            current_item["observation"] = final_observation
            set_conversation_state(phone, "awaiting_more_items", {
                "items": [current_item],
                "order_type": "DELIVERY"
            })
            return (
                f"Boa! 🍕 *Meio a Meio:*\n"
                f"½ {pizza1.name} + ½ {product.name}\n"
                f"💰 R$ {preco:.2f}\n"
                f"📝 _{final_observation}_\n\n"
                f"Mais alguma pizza?\n"
                f"1️⃣ Quero mais\n"
                f"2️⃣ Só isso"
            )

        set_conversation_state(phone, "awaiting_observation", {
            "order_type": "DELIVERY",
            "current_item": current_item,
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

    # Verifica se é pergunta (não deve ser tratada como observação)
    is_q, q_type, response = is_question(message)
    if is_q and response:
        return response + "\n\nDigite a observação ou 'não' se não tiver."

    # Saudações no meio = sem observação
    if is_greeting(message):
        message_lower = 'nao'

    state = get_conversation_state(phone)
    current_item = state["data"].get("current_item", {})
    items = state["data"].get("items", [])
    order_type = state["data"].get("order_type", "DELIVERY")

    # Salva observação no item atual
    if message_lower not in ['nao', 'não', 'n', 'nenhuma', 'nada', 'ok', 'nao tem', 'não tem']:
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
    pizzas = Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True).order_by('category', 'name')

    menu = "Boa escolha! 🔥 *2 Pizzas Grandes por R$ 55,00*\n\n"
    menu += "Escolhe o *primeiro* sabor:\n\n"
    for i, pizza in enumerate(pizzas, 1):
        menu += f"{i}. {pizza.name}\n"

    menu += "\n_Digite o número ou nome | 'voltar' | 'sair'_"

    set_conversation_state(phone, "awaiting_promo_pizza_1", {"promo": True})
    return menu


def handle_promo_pizza_1(phone: str, message: str) -> str:
    """Trata seleção da primeira pizza da promoção."""
    # Verifica inputs humanizados (perguntas, saudações)
    humanized_response = handle_humanized_input(phone, message, "awaiting_promo_pizza_1")
    if humanized_response:
        return humanized_response

    # Recupera itens existentes (para quando está adicionando mais promoções)
    state = get_conversation_state(phone)
    existing_items = state["data"].get("items", [])
    order_type = state["data"].get("order_type", "DELIVERY")

    # Verifica se digitou dois números (ex: "1 e 2", "1,2")
    two_numbers = parse_two_numbers(message)
    if two_numbers:
        num1, num2 = two_numbers
        pizzas = list(Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True).order_by('category', 'name'))
        if 1 <= num1 <= len(pizzas) and 1 <= num2 <= len(pizzas):
            pizza1 = pizzas[num1 - 1]
            pizza2 = pizzas[num2 - 1]
            set_conversation_state(phone, "awaiting_promo_half_or_full", {
                "promo": True,
                "pizza1_id": pizza1.id,
                "pizza2_id": pizza2.id,
                "pizza1_name": pizza1.name,
                "pizza2_name": pizza2.name,
                "existing_items": existing_items,
                "order_type": order_type,
            })
            return (
                f"Você escolheu *{pizza1.name}* e *{pizza2.name}*\n\n"
                f"Como você quer na promoção?\n\n"
                f"1️⃣ *Meio a meio* (uma pizza com metade de cada + uma inteira)\n"
                f"2️⃣ *Duas pizzas inteiras* (uma de cada sabor)\n\n"
                f"_'voltar' | 'cancelar'_"
            )

    # Verifica se digitou dois nomes de pizza (ex: "4 queijos e calabresa")
    two_pizzas = parse_two_pizza_names(message)
    if two_pizzas:
        pizza1, pizza2 = two_pizzas
        set_conversation_state(phone, "awaiting_promo_half_or_full", {
            "promo": True,
            "pizza1_id": pizza1.id,
            "pizza2_id": pizza2.id,
            "pizza1_name": pizza1.name,
            "pizza2_name": pizza2.name,
            "existing_items": existing_items,
            "order_type": order_type,
        })
        return (
            f"Você escolheu *{pizza1.name}* e *{pizza2.name}*\n\n"
            f"Como você quer na promoção?\n\n"
            f"1️⃣ *Meio a meio* (uma pizza com metade de cada + uma inteira)\n"
            f"2️⃣ *Duas pizzas inteiras* (uma de cada sabor)\n\n"
            f"_'voltar' | 'cancelar'_"
        )

    product, observation = find_product_with_observation(message)
    if not product:
        return "Hmm, não achei esse sabor 🤔 Pode repetir ou digitar o número do cardápio?\n\n_Dica: pode digitar '4 queijos e calabresa' para escolher dois sabores!_\n\n_'voltar' | 'sair'_"

    pizzas = Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True).order_by('category', 'name')

    obs_display = f" _{observation}_" if observation else ""
    menu = f"Boa! ✅ Primeira pizza: *{product.name}*{obs_display}\n\n"
    menu += "Agora escolhe o *segundo* sabor:\n\n"
    for i, pizza in enumerate(pizzas, 1):
        menu += f"{i}. {pizza.name}\n"

    menu += "\n_Dica: pode digitar '1 e 2' para meio a meio!_\n"
    menu += "_Digite o número ou nome | 'voltar' | 'sair'_"

    set_conversation_state(phone, "awaiting_promo_pizza_2", {
        "promo": True,
        "promo_pizza_1": product.id,
        "promo_pizza_1_obs": observation,
        "existing_items": existing_items,
        "order_type": order_type,
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
    existing_items = state["data"].get("existing_items", [])
    order_type = state["data"].get("order_type", "DELIVERY")

    # Observações já salvas anteriormente
    obs1 = state["data"].get("pizza1_obs", "")
    obs2 = state["data"].get("pizza2_obs", "")

    try:
        pizza1 = Product.objects.get(id=pizza1_id)
        pizza2 = Product.objects.get(id=pizza2_id)
    except Product.DoesNotExist:
        clear_conversation_state(phone)
        return "Ops, algo deu errado 😅 Vamos recomeçar!"

    promo_price = Decimal('27.50')

    # Detecta se é uma observação (ex: "calabresa sem cebola", "sem cebola na calabresa")
    obs_patterns = ['sem ', 'tirar ', 'com extra ', 'adicionar ', 'sem a ', 'tira ']
    has_observation = any(p in message_lower for p in obs_patterns)

    if has_observation:
        # Tenta identificar qual pizza a observação se refere
        pizza1_lower = pizza1.name.lower()
        pizza2_lower = pizza2.name.lower()

        # Extrai a observação
        _, observation = extract_observation(message)
        if not observation:
            observation = message_lower

        # Verifica se menciona qual pizza
        if pizza1_lower in message_lower or any(word in message_lower for word in pizza1_lower.split()):
            obs1 = observation
            pizza_ref = pizza1.name
        elif pizza2_lower in message_lower or any(word in message_lower for word in pizza2_lower.split()):
            obs2 = observation
            pizza_ref = pizza2.name
        else:
            # Não identificou qual pizza, assume a primeira
            obs1 = observation
            pizza_ref = pizza1.name

        # Salva observação no estado e pergunta novamente
        set_conversation_state(phone, "awaiting_promo_half_or_full", {
            **state["data"],
            "pizza1_obs": obs1,
            "pizza2_obs": obs2
        })

        obs_list = []
        if obs1:
            obs_list.append(f"• {pizza1.name}: _{obs1}_")
        if obs2:
            obs_list.append(f"• {pizza2.name}: _{obs2}_")
        obs_text = "\n".join(obs_list)

        return (
            f"Anotei! ✅ *{pizza_ref}*: _{observation}_\n\n"
            f"📝 *Observações:*\n{obs_text}\n\n"
            f"Agora escolhe como quer:\n"
            f"1️⃣ Meio a meio (uma pizza com metade de cada + uma inteira)\n"
            f"2️⃣ Duas pizzas inteiras (uma de cada sabor)\n\n"
            f"_'voltar' | 'cancelar'_"
        )

    # Meio a meio - uma pizza meio a meio + precisa escolher a segunda
    if message_lower in ['1', 'meio', 'metade', 'meio a meio', 'meia']:
        preco = max(pizza1.price, pizza2.price)
        obs_combined = []
        if obs1:
            obs_combined.append(f"{pizza1.name}: {obs1}")
        if obs2:
            obs_combined.append(f"{pizza2.name}: {obs2}")
        observation = " | ".join(obs_combined) if obs_combined else None

        new_items = existing_items + [{
            "type": "half_half",
            "pizza1_id": pizza1.id,
            "pizza2_id": pizza2.id,
            "pizza1_name": pizza1.name,
            "pizza2_name": pizza2.name,
            "price": float(promo_price),
            "promo_price": float(promo_price),
            "observation": observation
        }]
        set_conversation_state(phone, "awaiting_promo_second_after_half", {
            "promo": True,
            "items": new_items,
            "order_type": order_type,
        })
        pizzas = Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True).order_by('category', 'name')
        obs_msg = f"\n📝 _{observation}_" if observation else ""
        menu = (
            f"Boa! 🍕 Primeira pizza: *Meio a Meio*\n"
            f"½ {pizza1.name} + ½ {pizza2.name}{obs_msg}\n\n"
            f"Agora escolhe o sabor da *segunda pizza* da promoção:\n\n"
        )
        for i, pizza in enumerate(pizzas, 1):
            menu += f"{i}. {pizza.name}\n"
        menu += "\n_Digite o número ou nome | 'voltar' | 'sair'_"
        return menu

    # Duas pizzas inteiras
    if message_lower in ['2', 'duas', 'inteira', 'inteiras', 'separadas', 'separado']:
        new_items = existing_items + [
            {"product_id": pizza1.id, "quantity": 1, "promo_price": float(promo_price), "observation": obs1 or None},
            {"product_id": pizza2.id, "quantity": 1, "promo_price": float(promo_price), "observation": obs2 or None}
        ]
        set_conversation_state(phone, "awaiting_promo_more_items", {
            "items": new_items,
            "promo": True,
            "pizza_1_name": pizza1.name,
            "pizza_2_name": pizza2.name,
        })
        obs1_text = f" _{obs1}_" if obs1 else ""
        obs2_text = f" _{obs2}_" if obs2 else ""
        return (
            f"Perfeito! ✅\n\n"
            f"🍕 *{pizza1.name}*{obs1_text} + *{pizza2.name}*{obs2_text}\n"
            f"💰 *Total da promoção: R$ 55,00*\n\n"
            f"Quer adicionar mais pizza?\n"
            f"1️⃣ Mais promoção (2 por R$55)\n"
            f"2️⃣ Pizza avulsa\n"
            f"3️⃣ Não, só isso\n\n"
            f"_'voltar' | 'sair'_"
        )

    return "Não entendi 😅 Digite 1 para meio a meio ou 2 para duas pizzas inteiras.\n\n_'voltar' | 'cancelar'_"


def handle_promo_second_after_half(phone: str, message: str) -> str:
    """Trata seleção da segunda pizza após escolher meio a meio na promoção."""
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])
    order_type = state["data"].get("order_type", "DELIVERY")

    product, observation = find_product_with_observation(message)
    if not product:
        return "Hmm, não achei esse sabor 🤔 Pode repetir ou digitar o número do cardápio?\n\n_'voltar' | 'sair'_"

    promo_price = Decimal('27.50')
    new_item = {"product_id": product.id, "quantity": 1, "promo_price": float(promo_price)}
    if observation:
        new_item["observation"] = observation
    items.append(new_item)

    # Monta nomes para exibição - busca o último item half_half (da promoção atual)
    half_half = None
    for item in reversed(items):
        if item.get("type") == "half_half":
            half_half = item
            break

    pizza1_name = half_half.get("pizza1_name", "") if half_half else ""
    pizza2_name = half_half.get("pizza2_name", "") if half_half else ""

    set_conversation_state(phone, "awaiting_promo_more_items", {
        "items": items,
        "promo": True,
        "pizza_1_name": f"½ {pizza1_name} + ½ {pizza2_name}",
        "pizza_2_name": product.name,
    })

    obs_display = f" _{observation}_" if observation else ""
    return (
        f"Perfeito! ✅ Segunda pizza: *{product.name}*{obs_display}\n\n"
        f"🍕 *½ {pizza1_name} + ½ {pizza2_name}* (meio a meio)\n"
        f"🍕 *{product.name}*{obs_display}\n"
        f"💰 *Total da promoção: R$ 55,00*\n\n"
        f"Quer adicionar mais pizza?\n"
        f"1️⃣ Mais promoção (2 por R$55)\n"
        f"2️⃣ Pizza avulsa\n"
        f"3️⃣ Não, só isso\n\n"
        f"_'voltar' | 'sair'_"
    )


def handle_promo_pizza_2(phone: str, message: str) -> str:
    """Trata seleção da segunda pizza da promoção."""
    # Verifica inputs humanizados
    humanized_response = handle_humanized_input(phone, message, "awaiting_promo_pizza_2")
    if humanized_response:
        return humanized_response

    state = get_conversation_state(phone)
    pizza_1_id = state["data"].get("promo_pizza_1")
    existing_items = state["data"].get("existing_items", [])
    order_type = state["data"].get("order_type", "DELIVERY")
    logger.info(f"DEBUG handle_promo_pizza_2: message={repr(message)}, isdigit={message.strip().isdigit()}, pizza_1_id={pizza_1_id}")

    try:
        pizza_1 = Product.objects.get(id=pizza_1_id)
    except Product.DoesNotExist:
        clear_conversation_state(phone)
        return "Ops, algo deu errado 😅 Vamos recomeçar!"

    # Verifica se digitou dois números para meio a meio (ex: "1 e 4", "1,4")
    two_numbers = parse_two_numbers(message)
    if two_numbers:
        num1, num2 = two_numbers
        pizzas = list(Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True).order_by('category', 'name'))
        if 1 <= num1 <= len(pizzas) and 1 <= num2 <= len(pizzas):
            half_pizza1 = pizzas[num1 - 1]
            half_pizza2 = pizzas[num2 - 1]

            # Segunda pizza será meio a meio
            promo_price = Decimal('27.50')
            half_price = max(half_pizza1.price, half_pizza2.price)

            new_items = existing_items + [
                {"product_id": pizza_1.id, "quantity": 1, "promo_price": float(promo_price)},
                {
                    "type": "half_half",
                    "pizza1_id": half_pizza1.id,
                    "pizza2_id": half_pizza2.id,
                    "pizza1_name": half_pizza1.name,
                    "pizza2_name": half_pizza2.name,
                    "price": float(promo_price),
                    "quantity": 1
                }
            ]

            set_conversation_state(phone, "awaiting_promo_more_items", {
                "items": new_items,
                "promo": True,
                "pizza_1_name": pizza_1.name,
                "pizza_2_name": f"½ {half_pizza1.name} + ½ {half_pizza2.name}",
            })

            return (
                f"Perfeito! ✅ Segunda pizza: *½ {half_pizza1.name} + ½ {half_pizza2.name}*\n\n"
                f"🍕 *{pizza_1.name}* + *½ {half_pizza1.name} + ½ {half_pizza2.name}*\n"
                f"💰 *Total da promoção: R$ 55,00*\n\n"
                f"Quer adicionar mais pizza?\n"
                f"1️⃣ Mais promoção (2 por R$55)\n"
                f"2️⃣ Pizza avulsa\n"
                f"3️⃣ Não, só isso\n\n"
                f"_'voltar' | 'sair'_"
            )

    # Verifica se digitou dois nomes de pizza para meio a meio (ex: "4 queijos e calabresa")
    two_pizzas = parse_two_pizza_names(message)
    if two_pizzas:
        half_pizza1, half_pizza2 = two_pizzas

        # Segunda pizza será meio a meio
        promo_price = Decimal('27.50')

        new_items = existing_items + [
            {"product_id": pizza_1.id, "quantity": 1, "promo_price": float(promo_price)},
            {
                "type": "half_half",
                "pizza1_id": half_pizza1.id,
                "pizza2_id": half_pizza2.id,
                "pizza1_name": half_pizza1.name,
                "pizza2_name": half_pizza2.name,
                "price": float(promo_price),
                "quantity": 1
            }
        ]

        set_conversation_state(phone, "awaiting_promo_more_items", {
            "items": new_items,
            "promo": True,
            "pizza_1_name": pizza_1.name,
            "pizza_2_name": f"½ {half_pizza1.name} + ½ {half_pizza2.name}",
        })

        return (
            f"Perfeito! ✅ Segunda pizza: *½ {half_pizza1.name} + ½ {half_pizza2.name}*\n\n"
            f"🍕 *{pizza_1.name}* + *½ {half_pizza1.name} + ½ {half_pizza2.name}*\n"
            f"💰 *Total da promoção: R$ 55,00*\n\n"
            f"Quer adicionar mais pizza?\n"
            f"1️⃣ Mais promoção (2 por R$55)\n"
            f"2️⃣ Pizza avulsa\n"
            f"3️⃣ Não, só isso\n\n"
            f"_'voltar' | 'sair'_"
        )

    product, observation = find_product_with_observation(message)
    if not product:
        logger.warning(f"DEBUG: find_product_with_observation retornou None para '{message}'")
        return "Hmm, não achei esse sabor 🤔 Pode repetir ou digitar o número do cardápio?\n\n_Dica: pode digitar '4 queijos e calabresa' para meio a meio!_\n\n_'voltar' | 'sair'_"

    # Recupera observação da pizza 1 (se houver)
    pizza_1_obs = state["data"].get("promo_pizza_1_obs")

    # Define os itens com preço especial da promoção (R$ 27,50 cada = R$ 55 total)
    promo_price = Decimal('27.50')
    item_1 = {"product_id": pizza_1.id, "quantity": 1, "promo_price": float(promo_price)}
    item_2 = {"product_id": product.id, "quantity": 1, "promo_price": float(promo_price)}

    # Adiciona observações se existirem
    if pizza_1_obs:
        item_1["observation"] = pizza_1_obs
    if observation:
        item_2["observation"] = observation

    new_items = existing_items + [item_1, item_2]

    set_conversation_state(phone, "awaiting_promo_more_items", {
        "items": new_items,
        "promo": True,
        "pizza_1_name": pizza_1.name,
        "pizza_2_name": product.name,
    })

    # Exibe observações se existirem
    obs_1_display = f" _{pizza_1_obs}_" if pizza_1_obs else ""
    obs_2_display = f" _{observation}_" if observation else ""

    return (
        f"Perfeito! ✅ Segunda pizza: *{product.name}*{obs_2_display}\n\n"
        f"🍕 *{pizza_1.name}*{obs_1_display} + *{product.name}*{obs_2_display}\n"
        f"💰 *Total da promoção: R$ 55,00*\n\n"
        f"Quer adicionar mais pizza?\n"
        f"1️⃣ Mais promoção (2 por R$55)\n"
        f"2️⃣ Pizza avulsa\n"
        f"3️⃣ Não, só isso\n\n"
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

    # Detecta se cliente já mandou o endereço junto (ex: "entrega na rua das flores 123")
    address_indicators = ['rua ', 'av ', 'avenida ', 'travessa ', 'alameda ', 'estrada ']
    has_address = any(ind in message_lower for ind in address_indicators) or re.search(r'\d{2,5}', message)

    if has_address and any(word in message_lower for word in ['entrega', 'entregar', 'delivery', 'manda', 'leva']):
        # Cliente quer entrega e já mandou o endereço
        set_conversation_state(phone, "awaiting_address", {
            "items": items,
            "order_type": "DELIVERY",
            "promo": True,
            "pending_address": message  # Guarda para processar
        })
        # Processa o endereço diretamente
        return handle_awaiting_address(phone, message)

    # Se só tem indicador de endereço, assume entrega
    if has_address:
        set_conversation_state(phone, "awaiting_address", {
            "items": items,
            "order_type": "DELIVERY",
            "promo": True
        })
        return handle_awaiting_address(phone, message)

    return "Não entendi 😅 Digita 1 pra entrega ou 2 pra retirada!\n\n_'voltar' | 'sair'_"


def handle_more_promo(phone: str, message: str) -> str:
    """Trata pergunta se quer mais promoção."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])
    order_type = state["data"].get("order_type", "DELIVERY")

    # Quer mais promoção
    if message_lower in ['1', 'sim', 's', 'quero', 'mais']:
        # Mantém os itens já selecionados e inicia nova promoção
        set_conversation_state(phone, "awaiting_promo_pizza_1", {
            "items": items,
            "order_type": order_type,
            "promo": True
        })

        pizzas = Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True).order_by('category', 'name')
        menu = "Mais uma promoção! 🔥 Qual o *primeiro* sabor?\n\n"
        for i, pizza in enumerate(pizzas, 1):
            menu += f"{i}. {pizza.name}\n"
        menu += "\n_Dica: pode digitar '1 e 4' ou '4 queijos e calabresa' para meio a meio!_\n\n_'voltar' | 'sair'_"
        return menu

    # Não quer mais
    if message_lower in ['2', 'nao', 'não', 'n', 'so isso', 'só isso']:
        if order_type == "DELIVERY":
            set_conversation_state(phone, "awaiting_drink", {
                "items": items,
                "order_type": "DELIVERY",
                "promo": True
            })
        else:
            set_conversation_state(phone, "awaiting_drink_pickup", {
                "items": items,
                "order_type": "PICKUP",
                "promo": True
            })
        return get_drinks_menu()

    return "Não entendi 😅 Digita 1 pra mais promoção ou 2 pra continuar!\n\n_'voltar' | 'sair'_"


def handle_promo_more_items(phone: str, message: str) -> str:
    """Trata pergunta se quer mais pizzas após promoção (antes de escolher entrega/retirada)."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])
    pizza_1_name = state["data"].get("pizza_1_name", "")
    pizza_2_name = state["data"].get("pizza_2_name", "")

    # Opção 1: Mais uma promoção (2 pizzas por R$55)
    if message_lower in ['1', 'promocao', 'promoção', 'promo']:
        set_conversation_state(phone, "awaiting_promo_pizza_1", {
            "items": items,
            "promo": True,
        })

        pizzas = Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True).order_by('category', 'name')
        menu = "Mais uma promoção! 🔥 Qual o *primeiro* sabor?\n\n"
        for i, pizza in enumerate(pizzas, 1):
            menu += f"{i}. {pizza.name}\n"
        menu += "\n_Dica: pode digitar '1 e 4' ou '4 queijos e calabresa' para meio a meio!_\n\n_'voltar' | 'sair'_"
        return menu

    # Opção 2: Adicionar pizza avulsa
    if message_lower in ['2', 'avulsa', 'avulso', 'uma']:
        set_conversation_state(phone, "awaiting_promo_another_item", {
            "items": items,
            "promo": True,
            "pizza_1_name": pizza_1_name,
            "pizza_2_name": pizza_2_name,
        })

        pizzas = Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True).order_by('category', 'name')
        menu = "Beleza! Qual sabor avulso? 🍕\n\n"
        for i, pizza in enumerate(pizzas, 1):
            menu += f"{i}. {pizza.name} - R$ {pizza.price:.2f}\n"
        menu += "\n_Digite o número ou nome | 'voltar' | 'sair'_"
        return menu

    # Opção 3: Não quer mais
    if message_lower in ['3', 'nao', 'não', 'n', 'so isso', 'só isso', 'essa', 'so essa', 'só essa']:
        set_conversation_state(phone, "awaiting_promo_order_type", {
            "items": items,
            "promo": True,
            "pizza_1_name": pizza_1_name,
            "pizza_2_name": pizza_2_name,
        })
        return (
            f"Beleza! 👍\n\n"
            f"Vai ser pra *entrega* ou *retirada*? 🛵🏪\n\n"
            f"1️⃣ Entrega (delivery)\n"
            f"2️⃣ Retirada no local\n\n"
            f"_'voltar' | 'sair'_"
        )

    return "Não entendi 😅\n\n1️⃣ Mais promoção (2 por R$55)\n2️⃣ Pizza avulsa\n3️⃣ Não, só isso\n\n_'voltar' | 'sair'_"


def handle_promo_another_item(phone: str, message: str) -> str:
    """Trata adição de pizza extra após promoção."""
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])
    pizza_1_name = state["data"].get("pizza_1_name", "")
    pizza_2_name = state["data"].get("pizza_2_name", "")

    # Verifica se é pedido meio a meio
    if is_half_half_request(message):
        sabor1_text, sabor2_text = parse_half_half(message)
        if sabor1_text and sabor2_text:
            pizza1, obs1 = find_product_with_observation(sabor1_text)
            pizza2, obs2 = find_product_with_observation(sabor2_text)
            if pizza1 and pizza2:
                preco = max(pizza1.price, pizza2.price)

                # Combina observações
                combined_obs = []
                if obs1:
                    combined_obs.append(f"½ {pizza1.name}: {obs1}")
                if obs2:
                    combined_obs.append(f"½ {pizza2.name}: {obs2}")
                final_obs = "; ".join(combined_obs) if combined_obs else None

                new_item = {
                    "type": "half_half",
                    "pizza1_id": pizza1.id,
                    "pizza2_id": pizza2.id,
                    "pizza1_name": pizza1.name,
                    "pizza2_name": pizza2.name,
                    "price": float(preco),
                    "quantity": 1
                }
                if final_obs:
                    new_item["observation"] = final_obs
                items.append(new_item)

                set_conversation_state(phone, "awaiting_promo_more_items", {
                    "items": items,
                    "promo": True,
                    "pizza_1_name": pizza_1_name,
                    "pizza_2_name": pizza_2_name,
                })
                obs_display = f"\n📝 _{final_obs}_" if final_obs else ""
                return (
                    f"Anotado! ✅ *½ {pizza1.name} + ½ {pizza2.name}* - R$ {preco:.2f}{obs_display}\n\n"
                    f"Mais alguma pizza?\n"
                    f"1️⃣ Quero mais\n"
                    f"2️⃣ Só isso\n\n"
                    f"_'voltar' | 'sair'_"
                )

    product, observation = find_product_with_observation(message)
    if not product:
        return "Hmm, não achei esse sabor 🤔 Pode repetir ou digitar o número do cardápio?\n\n_'voltar' | 'sair'_"

    new_item = {"product_id": product.id, "quantity": 1}
    if observation:
        new_item["observation"] = observation
    items.append(new_item)

    set_conversation_state(phone, "awaiting_promo_more_items", {
        "items": items,
        "promo": True,
        "pizza_1_name": pizza_1_name,
        "pizza_2_name": pizza_2_name,
    })
    obs_display = f"\n📝 _{observation}_" if observation else ""
    return (
        f"Anotado! ✅ *{product.name}* - R$ {product.price:.2f}{obs_display}\n\n"
        f"Mais alguma pizza?\n"
        f"1️⃣ Quero mais\n"
        f"2️⃣ Só isso\n\n"
        f"_'voltar' | 'sair'_"
    )


def handle_awaiting_more_items(phone: str, message: str) -> str:
    """Trata pergunta se quer mais itens."""
    # Verifica inputs humanizados
    humanized_response = handle_humanized_input(phone, message, "awaiting_more_items")
    if humanized_response:
        return humanized_response

    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])
    order_type = state["data"].get("order_type", "DELIVERY")

    # Verifica se quer mais pizza
    if message_lower in ['1', 'sim', 's', 'quero', 'mais']:
        set_conversation_state(phone, "awaiting_another_item", {"items": items, "order_type": order_type})

        # Mostra cardápio resumido
        pizzas = Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True).order_by('category', 'name')
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
    product, observation = find_product_with_observation(message)
    if product:
        new_item = {"product_id": product.id, "quantity": 1}
        if observation:
            new_item["observation"] = observation
        items.append(new_item)
        set_conversation_state(phone, "awaiting_more_items", {"items": items, "order_type": order_type})
        obs_display = f"\n📝 _{observation}_" if observation else ""
        return (
            f"Anotado! ✅ *{product.name}* - R$ {product.price:.2f}{obs_display}\n\n"
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
            pizza1, obs1 = find_product_with_observation(sabor1_text)
            pizza2, obs2 = find_product_with_observation(sabor2_text)
            if pizza1 and pizza2:
                preco = max(pizza1.price, pizza2.price)

                # Combina observações
                combined_obs = []
                if obs1:
                    combined_obs.append(f"½ {pizza1.name}: {obs1}")
                if obs2:
                    combined_obs.append(f"½ {pizza2.name}: {obs2}")
                final_obs = "; ".join(combined_obs) if combined_obs else None

                current_item = {
                    "type": "half_half",
                    "pizza1_id": pizza1.id,
                    "pizza2_id": pizza2.id,
                    "pizza1_name": pizza1.name,
                    "pizza2_name": pizza2.name,
                    "price": float(preco)
                }

                # Se já tem observação, pula a etapa
                if final_obs:
                    current_item["observation"] = final_obs
                    items.append(current_item)
                    set_conversation_state(phone, "awaiting_more_items", {
                        "items": items,
                        "order_type": order_type
                    })
                    return (
                        f"Boa! 🍕 *Meio a Meio:*\n"
                        f"½ {pizza1.name} + ½ {pizza2.name}\n"
                        f"💰 R$ {preco:.2f}\n"
                        f"📝 _{final_obs}_\n\n"
                        f"Mais alguma pizza?\n"
                        f"1️⃣ Quero mais\n"
                        f"2️⃣ Só isso"
                    )

                set_conversation_state(phone, "awaiting_observation", {
                    "order_type": order_type,
                    "current_item": current_item,
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
        pizzas = Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True).order_by('category', 'name')
        menu = "Pizza meio a meio! 🍕\n\nEscolhe o *primeiro* sabor:\n\n"
        for i, pizza in enumerate(pizzas, 1):
            menu += f"{i}. {pizza.name}\n"
        menu += "\n_Digite o número ou nome | 'voltar' | 'sair'_"
        return menu

    product, observation = find_product_with_observation(message)
    if not product:
        return "Hmm, não achei esse sabor 🤔 Pode repetir ou digitar o número do cardápio?\n\n_Dica: pode pedir meio a meio! Ex: 'meio calabresa meio mussarela'_\n\n_'voltar' | 'sair'_"

    current_item = {
        "type": "single",
        "product_id": product.id,
        "price": float(product.price)
    }

    # Se já extraiu observação, inclui e pula etapa
    if observation:
        current_item["observation"] = observation
        items.append(current_item)
        set_conversation_state(phone, "awaiting_more_items", {
            "items": items,
            "order_type": order_type
        })
        obs_text = f"\n📝 _{observation}_"
        return (
            f"Boa! ✅ *{product.name}* - R$ {product.price:.2f}{obs_text}\n\n"
            f"Mais alguma pizza?\n"
            f"1️⃣ Quero mais\n"
            f"2️⃣ Só isso"
        )

    set_conversation_state(phone, "awaiting_observation", {
        "order_type": order_type,
        "current_item": current_item,
        "items": items
    })

    return (
        f"Boa! ✅ *{product.name}* - R$ {product.price:.2f}\n\n"
        f"Alguma observação? (tirar cebola, sem tomate, etc)\n\n"
        f"_Digite a observação ou 'não' se não tiver_"
    )


def handle_awaiting_items(phone: str, message: str, order_type: str) -> str:
    """Trata selecao de itens para retirada."""
    product, observation = find_product_with_observation(message)
    if not product:
        return "Hmm, não achei esse sabor 🤔 Pode repetir ou digitar o número do cardápio?\n\n_'voltar' | 'sair'_"

    state = get_conversation_state(phone)
    items = state["data"].get("items", [])

    new_item = {"product_id": product.id, "quantity": 1}
    if observation:
        new_item["observation"] = observation
    items.append(new_item)

    set_conversation_state(phone, "awaiting_more_items_pickup", {
        "items": items,
        "order_type": order_type
    })

    obs_display = f"\n📝 _{observation}_" if observation else ""
    return (
        f"Anotado! ✅ *{product.name}* - R$ {product.price:.2f}{obs_display}\n\n"
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
        pizzas = Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True).order_by('category', 'name')
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
    product, observation = find_product_with_observation(message)
    if product:
        new_item = {"product_id": product.id, "quantity": 1}
        if observation:
            new_item["observation"] = observation
        items.append(new_item)
        set_conversation_state(phone, "awaiting_more_items_pickup", {"items": items, "order_type": "PICKUP"})
        obs_display = f"\n📝 _{observation}_" if observation else ""
        return (
            f"Anotado! ✅ *{product.name}* - R$ {product.price:.2f}{obs_display}\n\n"
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
    order_type = state["data"].get("order_type", "DELIVERY")
    is_promo = state["data"].get("promo", False)

    drinks = list(Product.objects.filter(category='BEBIDA', active=True).order_by('name'))
    no_drink_option = str(len(drinks) + 1)

    # Verifica se não quer bebida - várias formas
    no_drink_variations = [
        no_drink_option, "nao", "não", "n", "nao obrigado", "não obrigado",
        "so pizza", "só pizza", "sem bebida", "nao quero", "não quero",
        "dispensa", "passa", "pula", "nenhuma", "nada"
    ]
    if message_lower in no_drink_variations or any(v in message_lower for v in ['so pizza', 'só pizza', 'sem bebida', 'nao quero bebida', 'não quero bebida']):
        set_conversation_state(phone, "awaiting_address", {"items": items, "order_type": order_type, "promo": is_promo})
        return "Beleza! 📍 Me passa o endereço completo pra entrega:\n(Rua, número e bairro)\n\n_'voltar' | 'sair'_"

    # Tenta encontrar a bebida
    drink = find_drink_by_option(message)
    if drink:
        items.append({"product_id": drink.id, "quantity": 1})
        set_conversation_state(phone, "awaiting_address", {"items": items, "order_type": order_type, "promo": is_promo})
        return f"Boa! ✅ *{drink.name}* adicionado!\n\n📍 Me passa o endereço completo pra entrega:\n(Rua, número e bairro)\n\n_'voltar' | 'sair'_"

    # Detecta se cliente já mandou o endereço junto com "sem bebida"
    address_indicators = ['rua ', 'av ', 'avenida ', 'travessa ', 'alameda ', 'estrada ']
    has_address = any(ind in message_lower for ind in address_indicators) or re.search(r'\d{2,5}', message)

    if has_address:
        # Cliente já mandou o endereço, pula bebida
        set_conversation_state(phone, "awaiting_address", {"items": items, "order_type": order_type, "promo": is_promo})
        return handle_awaiting_address(phone, message)

    # Não encontrou bebida válida
    return f"Não entendi 😅 Escolhe uma opção de 1 a {len(drinks)}, ou {no_drink_option} se não quiser bebida!\n\n_'voltar' | 'sair'_"


def handle_awaiting_drink_pickup(phone: str, message: str) -> str:
    """Trata selecao de bebida para retirada."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])
    is_promo = state["data"].get("promo", False)

    drinks = list(Product.objects.filter(category='BEBIDA', active=True).order_by('name'))
    no_drink_option = str(len(drinks) + 1)

    # Busca dados do cliente
    customer = Customer.objects.filter(phone=phone).first()
    customer_name = customer.name if customer else None

    # Verifica se não quer bebida - várias formas
    no_drink_variations = [
        no_drink_option, "nao", "não", "n", "nao obrigado", "não obrigado",
        "so pizza", "só pizza", "sem bebida", "nao quero", "não quero",
        "dispensa", "passa", "pula", "nenhuma", "nada"
    ]
    if message_lower in no_drink_variations or any(v in message_lower for v in ['so pizza', 'só pizza', 'sem bebida', 'nao quero bebida', 'não quero bebida']):
        set_conversation_state(phone, "confirming_pickup", {"items": items, "promo": is_promo})
        summary = format_order_summary(items, order_type='PICKUP', is_promo=is_promo, customer_name=customer_name, customer_phone=phone)
        return (
            f"Beleza! Olha o resumo do seu pedido:\n\n"
            f"{summary}\n\n"
            f"Tudo certo? Você vai *RETIRAR* aqui no local 🏪\n\n"
            f"📍 *Endereço:* {PICKUP_ADDRESS}\n"
            f"🗺️ {PICKUP_MAPS_LINK}\n\n"
            f"1️⃣ Confirmar pedido\n"
            f"2️⃣ Cancelar"
        )

    # Tenta encontrar a bebida
    drink = find_drink_by_option(message)
    if drink:
        items.append({"product_id": drink.id, "quantity": 1})
        set_conversation_state(phone, "confirming_pickup", {"items": items, "promo": is_promo})
        summary = format_order_summary(items, order_type='PICKUP', is_promo=is_promo, customer_name=customer_name, customer_phone=phone)
        return (
            f"Boa! ✅ *{drink.name}* adicionado!\n\n"
            f"Olha o resumo do seu pedido:\n\n"
            f"{summary}\n\n"
            f"Tudo certo? Você vai *RETIRAR* aqui no local 🏪\n\n"
            f"📍 *Endereço:* {PICKUP_ADDRESS}\n"
            f"🗺️ {PICKUP_MAPS_LINK}\n\n"
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
            f"Pedido confirmado! ✅🍕\n\n"
            f"Já tô preparando! Quando ficar pronto eu te aviso aqui, beleza?\n\n"
            f"📍 *Retirar em:* {PICKUP_ADDRESS}\n"
            f"🗺️ {PICKUP_MAPS_LINK}\n\n"
            f"A Pizzaria do Negão agradece! ❤️"
        )

    if message_lower in ['2', 'nao', 'não', 'n', 'cancelar']:
        clear_conversation_state(phone)
        return "Sem problemas! Pedido cancelado. Qualquer coisa é só chamar! 👋"

    return "Digita 1 pra confirmar ou 2 pra cancelar 😊\n\n_'voltar' | 'sair'_"


def handle_awaiting_address(phone: str, message: str) -> str:
    """Trata endereco de entrega."""
    # Verifica inputs humanizados
    humanized_response = handle_humanized_input(phone, message, "awaiting_address")
    if humanized_response:
        return humanized_response

    state = get_conversation_state(phone)
    items = state["data"].get("items", [])
    is_promo = state["data"].get("promo", False)
    message_lower = message.lower().strip()

    # Verifica se quer mudar para retirada
    if message_lower in ['retirada', 'retirar', 'buscar', 'pickup', 'retira']:
        set_conversation_state(phone, "awaiting_drink_pickup", {
            "items": items,
            "order_type": "PICKUP",
            "promo": is_promo
        })
        return (
            f"Beleza, vai retirar no local! 👍\n\n"
            f"📍 *Endereço:* {PICKUP_ADDRESS}\n"
            f"🗺️ {PICKUP_MAPS_LINK}\n\n"
            + get_drinks_menu()
        )

    # Verifica se o endereço é muito curto
    if len(message.strip()) < 10:
        return "Preciso do endereço completo 😅\nMe passa a rua, número e bairro!\n\n_'voltar' | 'sair'_"

    # Busca todos os bairros ativos
    all_fees = DeliveryFee.objects.filter(active=True).order_by('neighborhood')
    neighborhood = None
    fee_obj = None

    # Primeiro tenta encontrar o nome completo do bairro no endereço
    for fee in all_fees:
        if fee.neighborhood.lower() in message_lower:
            fee_obj = fee
            neighborhood = fee.neighborhood
            break

    # Se não encontrou, tenta buscar nas ÚLTIMAS palavras do endereço (onde geralmente fica o bairro)
    if not neighborhood:
        # Remove números e palavras comuns de endereço (inclui números por extenso comuns em nomes de ruas)
        palavras_ignorar = [
            'rua', 'avenida', 'av', 'travessa', 'tv', 'alameda', 'al', 'numero', 'num', 'nº', 'n',
            'casa', 'apt', 'apto', 'apartamento', 'bloco', 'bl', 'quadra', 'qd', 'lote', 'lt',
            'e', 'de', 'do', 'da', 'dos', 'das', 'meio',
            # Números por extenso (comuns em nomes de ruas)
            'zero', 'um', 'uma', 'dois', 'duas', 'tres', 'três', 'quatro', 'cinco',
            'seis', 'sete', 'oito', 'nove', 'dez', 'onze', 'doze', 'treze', 'quatorze', 'quinze',
            'primeiro', 'primeira', 'segundo', 'segunda', 'terceiro', 'terceira',
        ]
        words = [w for w in message_lower.replace(',', ' ').split() if w not in palavras_ignorar and not w.isdigit() and len(w) >= 4]

        # Busca do final para o início (bairro geralmente é a última palavra)
        for word in reversed(words):
            fee_obj = find_neighborhood_fee(word)
            if fee_obj:
                neighborhood = fee_obj.neighborhood
                break

    # Se ainda não encontrou o bairro, tenta fuzzy match ou mostra lista
    if not neighborhood or not fee_obj:
        bairros_disponiveis = list(all_fees)
        if bairros_disponiveis:
            # Tenta encontrar bairro similar (fuzzy match)
            words = [w for w in message_lower.replace(',', ' ').split() if len(w) >= 3]
            best_match = None
            best_score = 0

            for word in words:
                for fee in bairros_disponiveis:
                    bairro_lower = fee.neighborhood.lower()
                    # Calcula similaridade simples
                    if word in bairro_lower or bairro_lower in word:
                        score = 80
                    elif word[:3] == bairro_lower[:3]:  # Começa igual
                        score = 60
                    else:
                        # Conta letras em comum
                        common = sum(1 for c in word if c in bairro_lower)
                        score = (common / max(len(word), len(bairro_lower))) * 100

                    if score > best_score and score >= 50:
                        best_score = score
                        best_match = fee

            # Se encontrou um match razoável, sugere
            if best_match and best_score >= 50:
                set_conversation_state(phone, "awaiting_neighborhood_confirm", {
                    "items": items,
                    "address": message,
                    "suggested_neighborhood": best_match.neighborhood,
                    "suggested_fee": float(best_match.fee),
                    "promo": is_promo
                })
                return (
                    f"🤔 Não encontrei o bairro exato...\n\n"
                    f"Você quis dizer *{best_match.neighborhood}*?\n"
                    f"(Taxa de entrega: R$ {best_match.fee:.2f})\n\n"
                    f"1️⃣ Sim, é esse\n"
                    f"2️⃣ Não, vou digitar o bairro\n\n"
                    f"_Ou digite 'retirada' para buscar no local_"
                )

            # Se não encontrou match, mostra lista numerada
            bairros_lista = "\n".join([f"{i+1}. {f.neighborhood} (R$ {f.fee:.2f})" for i, f in enumerate(bairros_disponiveis)])
            set_conversation_state(phone, "awaiting_neighborhood_select", {
                "items": items,
                "address": message,
                "promo": is_promo
            })
            return (
                f"😕 Não encontrei o bairro no seu endereço.\n\n"
                f"*Digite o número* do seu bairro:\n\n{bairros_lista}\n\n"
                f"_Ou digite 'retirada' para buscar no local_\n"
                f"_'voltar' | 'sair'_"
            )
        else:
            return "Não há bairros cadastrados para entrega. Entre em contato pelo telefone."

    delivery_fee = fee_obj.fee

    set_conversation_state(phone, "confirming_delivery", {
        "items": items,
        "address": message,
        "neighborhood": neighborhood,
        "delivery_fee": float(delivery_fee),
        "promo": is_promo
    })

    # Busca dados do cliente
    customer = Customer.objects.filter(phone=phone).first()
    customer_name = customer.name if customer else None

    summary = format_order_summary(items, delivery_fee, order_type='DELIVERY', is_promo=is_promo, customer_name=customer_name, customer_phone=phone)

    return (
        f"Beleza! Olha o resumo do seu pedido:\n\n"
        f"{summary}\n\n"
        f"📍 *Endereço:* {message}\n"
        f"🏘️ *Bairro:* {neighborhood}\n\n"
        f"Tudo certo pra *ENTREGA*? 🛵\n"
        f"1️⃣ Confirmar pedido\n"
        f"2️⃣ Cancelar"
    )


def handle_neighborhood_confirm(phone: str, message: str) -> str:
    """Trata confirmação de bairro sugerido."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])
    address = state["data"].get("address", "")
    suggested = state["data"].get("suggested_neighborhood", "")
    fee = state["data"].get("suggested_fee", 0)
    is_promo = state["data"].get("promo", False)

    # Verifica se quer retirada
    if message_lower in ['retirada', 'retirar', 'buscar']:
        set_conversation_state(phone, "awaiting_drink_pickup", {
            "items": items,
            "order_type": "PICKUP",
            "promo": is_promo
        })
        return f"Beleza, vai retirar no local! 👍\n\n" + get_drinks_menu()

    # Confirma o bairro sugerido
    if message_lower in ['1', 'sim', 's', 'esse', 'é esse', 'e esse']:
        set_conversation_state(phone, "confirming_delivery", {
            "items": items,
            "address": address,
            "neighborhood": suggested,
            "delivery_fee": fee,
            "promo": is_promo
        })

        customer = Customer.objects.filter(phone=phone).first()
        customer_name = customer.name if customer else None
        summary = format_order_summary(items, Decimal(str(fee)), order_type='DELIVERY', is_promo=is_promo, customer_name=customer_name, customer_phone=phone)

        return (
            f"Beleza! Olha o resumo do seu pedido:\n\n"
            f"{summary}\n\n"
            f"📍 *Endereço:* {address}\n"
            f"🏘️ *Bairro:* {suggested}\n\n"
            f"Tudo certo pra *ENTREGA*? 🛵\n"
            f"1️⃣ Confirmar pedido\n"
            f"2️⃣ Cancelar"
        )

    # Quer digitar outro bairro
    if message_lower in ['2', 'nao', 'não', 'n', 'outro']:
        all_fees = DeliveryFee.objects.filter(active=True).order_by('neighborhood')
        bairros_lista = "\n".join([f"{i+1}. {f.neighborhood} (R$ {f.fee:.2f})" for i, f in enumerate(all_fees)])
        set_conversation_state(phone, "awaiting_neighborhood_select", {
            "items": items,
            "address": address,
            "promo": is_promo
        })
        return (
            f"*Digite o número* do seu bairro:\n\n{bairros_lista}\n\n"
            f"_Ou digite o nome do bairro_\n"
            f"_'voltar' | 'sair'_"
        )

    return "Não entendi 😅\n\n1️⃣ Sim, é esse bairro\n2️⃣ Não, vou escolher outro"


def handle_neighborhood_select(phone: str, message: str) -> str:
    """Trata seleção de bairro da lista."""
    message_lower = message.lower().strip()
    state = get_conversation_state(phone)
    items = state["data"].get("items", [])
    address = state["data"].get("address", "")
    is_promo = state["data"].get("promo", False)

    # Verifica se quer retirada
    if message_lower in ['retirada', 'retirar', 'buscar']:
        set_conversation_state(phone, "awaiting_drink_pickup", {
            "items": items,
            "order_type": "PICKUP",
            "promo": is_promo
        })
        return f"Beleza, vai retirar no local! 👍\n\n" + get_drinks_menu()

    all_fees = list(DeliveryFee.objects.filter(active=True).order_by('neighborhood'))

    # Se digitou número
    if message_lower.isdigit():
        idx = int(message_lower)
        if 1 <= idx <= len(all_fees):
            fee_obj = all_fees[idx - 1]
            set_conversation_state(phone, "confirming_delivery", {
                "items": items,
                "address": address,
                "neighborhood": fee_obj.neighborhood,
                "delivery_fee": float(fee_obj.fee),
                "promo": is_promo
            })

            customer = Customer.objects.filter(phone=phone).first()
            customer_name = customer.name if customer else None
            summary = format_order_summary(items, fee_obj.fee, order_type='DELIVERY', is_promo=is_promo, customer_name=customer_name, customer_phone=phone)

            return (
                f"Beleza! Olha o resumo do seu pedido:\n\n"
                f"{summary}\n\n"
                f"📍 *Endereço:* {address}\n"
                f"🏘️ *Bairro:* {fee_obj.neighborhood}\n\n"
                f"Tudo certo pra *ENTREGA*? 🛵\n"
                f"1️⃣ Confirmar pedido\n"
                f"2️⃣ Cancelar"
            )

    # Se digitou nome do bairro
    for fee_obj in all_fees:
        if fee_obj.neighborhood.lower() in message_lower or message_lower in fee_obj.neighborhood.lower():
            set_conversation_state(phone, "confirming_delivery", {
                "items": items,
                "address": address,
                "neighborhood": fee_obj.neighborhood,
                "delivery_fee": float(fee_obj.fee),
                "promo": is_promo
            })

            customer = Customer.objects.filter(phone=phone).first()
            customer_name = customer.name if customer else None
            summary = format_order_summary(items, fee_obj.fee, order_type='DELIVERY', is_promo=is_promo, customer_name=customer_name, customer_phone=phone)

            return (
                f"Beleza! Olha o resumo do seu pedido:\n\n"
                f"{summary}\n\n"
                f"📍 *Endereço:* {address}\n"
                f"🏘️ *Bairro:* {fee_obj.neighborhood}\n\n"
                f"Tudo certo pra *ENTREGA*? 🛵\n"
                f"1️⃣ Confirmar pedido\n"
                f"2️⃣ Cancelar"
            )

    # Não encontrou
    bairros_lista = "\n".join([f"{i+1}. {f.neighborhood} (R$ {f.fee:.2f})" for i, f in enumerate(all_fees)])
    return (
        f"Não encontrei esse bairro 😕\n\n"
        f"*Digite o número* do seu bairro:\n\n{bairros_lista}\n\n"
        f"_'voltar' | 'sair'_"
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

        set_conversation_state(phone, "awaiting_payment_choice", {"order_id": order.id})

        return (
            f"Pedido confirmado! ✅\n\n"
            f"💰 *Como vai ser o pagamento?*\n\n"
            f"1️⃣ *PIX* (envia comprovante)\n"
            f"2️⃣ *Dinheiro* (paga na entrega)\n"
            f"3️⃣ *Cartão Crédito* (+R$ 2,00 taxa maquininha)\n"
            f"4️⃣ *Cartão Débito* (+R$ 2,00 taxa maquininha)\n\n"
            f"_'voltar' | 'cancelar'_"
        )

    if message_lower in ['2', 'nao', 'não', 'n', 'cancelar']:
        clear_conversation_state(phone)
        return "Sem problemas! Pedido cancelado. Qualquer coisa é só chamar! 👋"

    return "Digita 1 pra confirmar ou 2 pra cancelar 😊\n\n_'voltar' | 'sair'_"


def handle_payment_choice(phone: str, message: str) -> str:
    """Trata escolha da forma de pagamento."""
    message_lower = message.lower().strip()
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

    settings_obj = BusinessSettings.get_settings()

    # 1. PIX - aceita várias formas
    pix_variations = ['1', 'pix', 'quero pix', 'pelo pix', 'no pix', 'via pix', 'transferencia', 'transferência']
    if any(v in message_lower for v in pix_variations) or message_lower == 'pix':
        order.payment_method = 'PIX'
        order.save()
        set_conversation_state(phone, "awaiting_receipt", {"order_id": order.id})
        return (
            f"Beleza! 💰 *Pagamento via PIX:*\n\n"
            f"Chave: *{settings_obj.pix_key}*\n"
            f"Nome: {settings_obj.pix_name}\n\n"
            f"Me manda o *comprovante* (foto) aqui pra eu liberar seu pedido! 📸"
        )

    # 2. Dinheiro - aceita várias formas
    cash_variations = ['2', 'dinheiro', 'cash', 'em dinheiro', 'no dinheiro', 'especie', 'espécie', 'na entrega']
    if any(v in message_lower for v in cash_variations) and 'cartao' not in message_lower and 'cartão' not in message_lower:
        order.payment_method = 'CASH'
        order.payment_status = 'PAY_ON_DELIVERY'
        order.save()
        set_conversation_state(phone, "awaiting_change", {"order_id": order.id})
        return (
            f"Beleza! 💵 *Pagamento em dinheiro na entrega.*\n\n"
            f"Vai precisar de troco? Se sim, pra quanto?\n\n"
            f"_Digite o valor (ex: 100) ou 'não' se não precisar_"
        )

    # 3. Cartão Crédito - aceita várias formas
    credit_variations = ['3', 'credito', 'crédito', 'cartao credito', 'cartão crédito', 'cartao de credito', 'cartão de crédito', 'no credito', 'no crédito']
    if any(v in message_lower for v in credit_variations):
        order.payment_method = 'CREDIT'
        order.payment_status = 'PAY_ON_DELIVERY'
        order.card_fee = Decimal('2.00')
        order.total = order.total + Decimal('2.00')
        order.status = 'PREPARING'
        order.save()
        clear_conversation_state(phone)

        return (
            f"Pedido confirmado! ✅\n\n"
            f"💳 *Pagamento: Cartão de Crédito*\n"
            f"(+R$ 2,00 taxa maquininha)\n\n"
            f"*Total: R$ {order.total:.2f}*\n\n"
            f"Seu pedido já está sendo preparado! 🍕\n"
            f"Tempo estimado: 50-70 minutos\n\n"
            f"Obrigado pela preferência! 😊"
        )

    # 4. Cartão Débito - aceita várias formas
    debit_variations = ['4', 'debito', 'débito', 'cartao debito', 'cartão débito', 'cartao de debito', 'cartão de débito', 'no debito', 'no débito']
    if any(v in message_lower for v in debit_variations):
        order.payment_method = 'DEBIT'
        order.payment_status = 'PAY_ON_DELIVERY'
        order.card_fee = Decimal('2.00')
        order.total = order.total + Decimal('2.00')
        order.status = 'PREPARING'
        order.save()
        clear_conversation_state(phone)

        return (
            f"Pedido confirmado! ✅\n\n"
            f"💳 *Pagamento: Cartão de Débito*\n"
            f"(+R$ 2,00 taxa maquininha)\n\n"
            f"*Total: R$ {order.total:.2f}*\n\n"
            f"Seu pedido já está sendo preparado! 🍕\n"
            f"Tempo estimado: 50-70 minutos\n\n"
            f"Obrigado pela preferência! 😊"
        )

    # Cartão genérico - pergunta crédito ou débito
    card_variations = ['cartao', 'cartão', 'maquininha', 'maquina', 'máquina', 'card']
    if any(v in message_lower for v in card_variations):
        set_conversation_state(phone, "awaiting_card_type", {"order_id": order.id})
        return (
            f"Cartão! 💳 Qual tipo?\n\n"
            f"1️⃣ Crédito\n"
            f"2️⃣ Débito\n\n"
            f"_(+R$ 2,00 taxa maquininha)_"
        )

    return (
        "Não entendi 😅 Escolhe uma opção:\n\n"
        "1️⃣ PIX\n"
        "2️⃣ Dinheiro\n"
        "3️⃣ Cartão Crédito\n"
        "4️⃣ Cartão Débito\n\n"
        "_'voltar' | 'cancelar'_"
    )


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
            f"Seu pedido está sendo analisado. 🔍\n\n"
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
        customer_name = order.customer.name if order.customer else None
        customer_phone = order.customer.phone if order.customer else phone
        summary = format_order_summary(items_data, order.delivery_fee, order_type='DELIVERY', customer_name=customer_name, customer_phone=customer_phone)
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
            f"Pedido confirmado! 💵\n\n"
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
            f"Pedido confirmado! 💵\n\n"
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
    credit_variations = ['1', 'credito', 'crédito', 'cred', 'no credito', 'no crédito', 'de credito', 'de crédito']
    debit_variations = ['2', 'debito', 'débito', 'deb', 'no debito', 'no débito', 'de debito', 'de débito']

    if any(v in message_lower for v in credit_variations):
        card_type = 'CREDIT'
        card_name = 'Crédito'
    elif any(v in message_lower for v in debit_variations):
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
        f"Pedido confirmado! 💳\n\n"
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
    pizzas = Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True).order_by('category', 'name')
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

    pizzas = Product.objects.filter(category__in=['PIZZA', 'PIZZA_DOCE'], active=True).order_by('category', 'name')
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


def is_valid_chat_id(chat_id: str) -> bool:
    """Verifica se é um chat_id válido (telefone ou LID)."""
    if not chat_id:
        return False

    # Aceita LIDs
    if '@lid' in chat_id.lower():
        return True

    # Aceita formatos completos do WhatsApp
    if '@c.us' in chat_id or '@s.whatsapp.net' in chat_id:
        return True

    # Verifica se tem dígitos suficientes
    digits = ''.join(filter(str.isdigit, chat_id))
    return len(digits) >= 8


def extract_chat_id(payload: dict) -> str:
    """Extrai o chat_id do payload do WAHA. Aceita telefones e LIDs."""
    _data = payload.get('_data', {})
    info = _data.get('Info', {})

    logger.info(f"DEBUG extract_chat_id - payload keys: {list(payload.keys())}")

    # Lista de campos para tentar extrair o chat_id (em ordem de prioridade)
    candidates = [
        payload.get('chatId', ''),  # Campo principal
        payload.get('from', ''),  # Pode ser número ou LID
        info.get('RemoteJid', ''),  # Formato: 5569993639552@s.whatsapp.net ou LID@lid
        _data.get('RemoteJid', ''),  # Backup
        payload.get('participant', ''),  # Em grupos
    ]

    logger.info(f"DEBUG extract_chat_id - candidates: {candidates}")

    for candidate in candidates:
        if not candidate:
            continue

        # Se é um LID, aceita diretamente
        if '@lid' in candidate.lower():
            logger.info(f"Chat ID (LID) extraido: {candidate}")
            return candidate

        # Se já está no formato correto do WhatsApp
        if '@c.us' in candidate or '@s.whatsapp.net' in candidate:
            # Extrai a parte antes do @
            parts = candidate.split('@')
            chat_part = parts[0].split(':')[0]  # Remove :XX se existir
            suffix = '@' + parts[1]

            if is_valid_chat_id(chat_part + suffix):
                result = chat_part + suffix
                logger.info(f"Chat ID extraido: {result}")
                return result

        # Tenta extrair número puro
        phone = re.sub(r'[@:].*', '', candidate)
        if not phone.isdigit():
            phone = re.sub(r'\D', '', phone)

        # Valida comprimento (telefones: 8-15, LIDs numéricos: até 20)
        if len(phone) >= 8 and len(phone) <= 20:
            # Adiciona sufixo padrão
            result = f"{phone}@c.us"
            logger.info(f"Chat ID construido: {result} (de {candidate})")
            return result

    logger.warning(f"Nao foi possivel extrair chat_id valido do payload")
    return None


# Alias para compatibilidade
def is_valid_phone(phone: str) -> bool:
    """Alias para is_valid_chat_id - mantido para compatibilidade."""
    return is_valid_chat_id(phone)


def extract_phone_number(payload: dict) -> str:
    """Alias para extract_chat_id - mantido para compatibilidade."""
    return extract_chat_id(payload)


def process_n8n_envelope(data: dict) -> JsonResponse:
    """
    Processa envelope estruturado do n8n (novo formato híbrido).

    Envelope esperado:
    {
        "source": "n8n",
        "normalized": { phone, text, ... },
        "buffer": { combined_text, messages_count, ... },
        "routing": { used_llm, reason },
        "llm": { provider, model, valid, result: { intent, entities, ... } },
        "address_resolution": { matched_neighborhood, delivery_fee, ... }
    }
    """
    normalized = data.get('normalized', {})
    buffer = data.get('buffer', {})
    routing = data.get('routing', {})
    llm = data.get('llm')
    address_resolution = data.get('address_resolution')

    phone = normalized.get('phone', '')
    text = buffer.get('combined_text') or normalized.get('text', '')
    msg_type = normalized.get('msg_type', 'chat')
    customer_name = normalized.get('customer_name', '')

    logger.info(f"[N8N] Processando envelope: phone={phone}, used_llm={routing.get('used_llm')}, reason={routing.get('reason')}")

    # Verifica se o chatbot está ativo
    settings_obj = BusinessSettings.get_settings()
    if not settings_obj.chatbot_enabled:
        logger.info("Chatbot desativado - mensagem ignorada")
        return JsonResponse({"status": "ignored", "reason": "chatbot_disabled"})

    # Cria/atualiza cliente
    if customer_name:
        get_or_create_customer(phone, customer_name)

    # IMPORTANTE: Verifica estado atual ANTES de decidir usar LLM
    # Se estiver em fluxo de promoção ou outros estados específicos, usa fluxo padrão
    current_state = get_conversation_state(phone).get('state', 'welcome')

    # Estados que devem SEMPRE usar o fluxo padrão (não LLM)
    priority_states = [
        'awaiting_promo_pizza_1', 'awaiting_promo_pizza_2', 'awaiting_promo_more_items',
        'awaiting_promo_another_item', 'awaiting_promo_order_type', 'awaiting_more_promo',
        'awaiting_promo_half_or_full', 'awaiting_promo_second_after_half',
        'awaiting_half_half_first', 'awaiting_half_half_second',
        'awaiting_observation', 'awaiting_address', 'awaiting_payment',
        'awaiting_change', 'awaiting_card_type', 'awaiting_confirmation',
        'awaiting_neighborhood_confirm', 'awaiting_neighborhood_select',
        'awaiting_more_items', 'awaiting_another_item', 'awaiting_drink',
        'confirming_delivery', 'confirming_pickup', 'awaiting_payment_choice',
        'awaiting_receipt', 'awaiting_payment_method'
    ]

    if current_state in priority_states:
        logger.info(f"[N8N] Estado prioritário '{current_state}' - ignorando LLM, usando fluxo padrão")
        return process_standard_message(phone, text, msg_type)

    # Se NÃO usou LLM, processa normalmente (fluxo de estados)
    if not routing.get('used_llm'):
        return process_standard_message(phone, text, msg_type)

    # Se usou LLM mas falhou validação, usa fallback
    if llm and not llm.get('valid'):
        logger.warning(f"[N8N] LLM inválido: {llm.get('validation_error')}")
        return process_standard_message(phone, text, msg_type)

    # Processa resultado do LLM
    llm_result = llm.get('result', {}) if llm else {}
    intent = llm_result.get('intent', 'other')
    entities = llm_result.get('entities', {})

    logger.info(f"[N8N] Intent={intent}, confidence={llm_result.get('confidence')}")

    # Se tem resolução de endereço com match
    if address_resolution and address_resolution.get('status') == 'matched':
        matched = address_resolution.get('matched_neighborhood')
        fee = address_resolution.get('delivery_fee')
        logger.info(f"[N8N] Bairro matched: {matched}, fee={fee}")

        # Atualiza estado com endereço resolvido
        state = get_conversation_state(phone)
        address_data = entities.get('address', {})

        # Monta endereço completo
        full_address = f"{address_data.get('address_line', '')} {address_data.get('number', '')}".strip()
        if address_data.get('complement'):
            full_address += f", {address_data.get('complement')}"

        set_conversation_state(phone, state.get('state', 'welcome'), {
            'address': full_address,
            'neighborhood': matched,
            'delivery_fee': float(fee) if fee else 0
        })

    # Se tem resolução de endereço que precisa confirmação
    if address_resolution and address_resolution.get('status') == 'needs_confirmation':
        candidates = address_resolution.get('candidates', [])[:3]
        if candidates:
            options = "\n".join([f"{i+1}. {c['name']} (R$ {c['fee']:.2f})" for i, c in enumerate(candidates)])
            response = f"Não encontrei o bairro exato. Qual destes é o seu?\n\n{options}\n\nOu digite o nome correto."
            send_whatsapp_message(phone, response)
            return JsonResponse({"status": "ok", "action": "neighborhood_confirmation"})

    # Se tem resolução de endereço não encontrado
    if address_resolution and address_resolution.get('status') == 'not_found':
        response = "Não consegui identificar o bairro. Por favor, digite apenas o nome do bairro (ex: Planalto, Aponia)."
        send_whatsapp_message(phone, response)
        return JsonResponse({"status": "ok", "action": "neighborhood_retry"})

    # Processa intent do pedido
    order_entities = entities.get('order', {})
    items = order_entities.get('items', [])

    if intent == 'add_item' and items:
        return process_llm_add_item(phone, items, order_entities)

    if intent == 'order_build' and items:
        return process_llm_order_build(phone, items, order_entities)

    if intent == 'provide_address':
        return process_llm_address(phone, entities.get('address', {}), address_resolution)

    if intent == 'choose_payment':
        payment = entities.get('payment_method', 'unknown')
        if payment != 'unknown':
            return process_llm_payment(phone, payment, entities.get('change_for'))

    if intent == 'provide_change':
        change = entities.get('change_for')
        if change:
            return process_llm_change(phone, change)

    # Para outros intents ou baixa confiança, usa fluxo normal
    logger.info(f"[N8N] Fallback para fluxo normal: intent={intent}")
    return process_standard_message(phone, text, msg_type)


def process_standard_message(phone: str, text: str, msg_type: str) -> JsonResponse:
    """Processa mensagem pelo fluxo de estados padrão."""
    state = get_conversation_state(phone)
    current_state = state.get("state", "welcome")

    logger.info(f"[Standard] phone={phone}, state={current_state}, text={text[:50]}...")

    # Verifica comandos especiais
    if is_cancel_command(text):
        response = handle_cancel(phone)
        send_whatsapp_message(phone, response)
        return JsonResponse({"status": "ok"})

    if is_back_command(text):
        success, response = go_back_state(phone)
        send_whatsapp_message(phone, response)
        return JsonResponse({"status": "ok"})

    # Processa de acordo com o estado
    response = dispatch_state_handler(phone, text, msg_type, current_state)

    if response:
        send_whatsapp_message(phone, response)

    return JsonResponse({"status": "ok"})


def dispatch_state_handler(phone: str, text: str, msg_type: str, current_state: str) -> str:
    """Despacha para o handler correto baseado no estado."""
    handlers = {
        "welcome": lambda: handle_welcome(phone, text, msg_type),
        "awaiting_pickup_items": lambda: handle_awaiting_items(phone, text, "PICKUP"),
        "awaiting_promo_pizza_1": lambda: handle_promo_pizza_1(phone, text),
        "awaiting_promo_pizza_2": lambda: handle_promo_pizza_2(phone, text),
        "awaiting_promo_more_items": lambda: handle_promo_more_items(phone, text),
        "awaiting_promo_another_item": lambda: handle_promo_another_item(phone, text),
        "awaiting_promo_order_type": lambda: handle_promo_order_type(phone, text),
        "awaiting_more_promo": lambda: handle_more_promo(phone, text),
        "awaiting_half_half_first": lambda: handle_half_half_first(phone, text),
        "awaiting_half_half_second": lambda: handle_half_half_second(phone, text),
        "awaiting_observation": lambda: handle_observation(phone, text),
        "awaiting_more_items": lambda: handle_awaiting_more_items(phone, text),
        "awaiting_another_item": lambda: handle_awaiting_another_item(phone, text),
        "awaiting_more_items_pickup": lambda: handle_awaiting_more_items_pickup(phone, text),
        "awaiting_drink": lambda: handle_awaiting_drink(phone, text),
        "awaiting_drink_pickup": lambda: handle_awaiting_drink_pickup(phone, text),
        "awaiting_address": lambda: handle_awaiting_address(phone, text),
        "awaiting_neighborhood_confirm": lambda: handle_neighborhood_confirm(phone, text),
        "awaiting_neighborhood_select": lambda: handle_neighborhood_select(phone, text),
        "confirming_delivery": lambda: handle_confirming_delivery(phone, text),
        "confirming_pickup": lambda: handle_confirming_pickup(phone, text),
        "awaiting_payment_choice": lambda: handle_payment_choice(phone, text),
        "awaiting_receipt": lambda: handle_awaiting_receipt(phone, text, msg_type, None),
        "awaiting_payment_method": lambda: handle_payment_method(phone, text),
        "awaiting_change": lambda: handle_awaiting_change(phone, text),
        "awaiting_card_type": lambda: handle_card_type(phone, text),
        "awaiting_half_or_full": lambda: handle_half_or_full(phone, text),
        "awaiting_promo_half_or_full": lambda: handle_promo_half_or_full(phone, text),
        "awaiting_promo_second_after_half": lambda: handle_promo_second_after_half(phone, text),
    }

    handler = handlers.get(current_state, lambda: handle_welcome(phone, text, msg_type))
    return handler()


def process_llm_add_item(phone: str, items: list, order_entities: dict) -> JsonResponse:
    """Processa intent add_item do LLM."""
    state = get_conversation_state(phone)
    current_items = state.get("data", {}).get("items", [])

    for item in items:
        product = find_product_fuzzy(item.get('name', ''))
        if product:
            new_item = {
                "type": "single",
                "product_id": product.id,
                "quantity": item.get('quantity', 1),
                "price": float(product.price)
            }

            # Processa modifiers (ignora se ingredient estiver vazio)
            modifiers = item.get('modifiers', [])
            obs_parts = []
            for mod in modifiers:
                ingredient = mod.get('ingredient', '').strip()
                if ingredient:  # Só adiciona se tiver ingrediente
                    if mod.get('type') == 'remove':
                        obs_parts.append(f"sem {ingredient}")
                    elif mod.get('type') == 'add':
                        obs_parts.append(f"com {ingredient}")

            notes = (item.get('notes') or '').strip()
            if obs_parts or notes:
                obs = ', '.join(obs_parts)
                if notes:
                    obs = f"{obs} - {notes}" if obs else notes
                new_item['observation'] = obs

            current_items.append(new_item)
            logger.info(f"[LLM] Adicionado: {product.name} x{new_item['quantity']}")

    if current_items:
        set_conversation_state(phone, "awaiting_more_items", {
            "items": current_items,
            "order_type": state.get("data", {}).get("order_type", "DELIVERY")
        })

        # Monta resumo
        summary = "Anotado! ✅\n\n"
        for item in current_items[-len(items):]:  # Só os novos
            try:
                product = Product.objects.get(id=item["product_id"])
                qty = item.get('quantity', 1)
                summary += f"• {qty}x *{product.name}* - R$ {product.price:.2f}\n"
                obs = item.get('observation', '').strip()
                if obs:
                    summary += f"  📝 {obs}\n"
            except:
                pass

        # Se for ambíguo, pergunta
        if order_entities.get('ambiguous'):
            reason = order_entities.get('ambiguity_reason', '')
            if reason:
                summary += f"\n⚠️ {reason}\n\n"
            else:
                summary += "\n⚠️ Detectei mais de um sabor.\n\n"
            summary += "É *meio a meio* ou *duas pizzas* separadas?\n"
            summary += "1️⃣ Meio a meio\n"
            summary += "2️⃣ Duas separadas"
            set_conversation_state(phone, "awaiting_half_or_full", state.get("data", {}))
        else:
            summary += "\nQuer mais alguma pizza?\n"
            summary += "1️⃣ Quero mais\n"
            summary += "2️⃣ Só isso"

        send_whatsapp_message(phone, summary)
        return JsonResponse({"status": "ok", "action": "item_added"})

    # Fallback se não encontrou nenhum produto
    return process_standard_message(phone, items[0].get('name', ''), 'chat')


def process_llm_order_build(phone: str, items: list, order_entities: dict) -> JsonResponse:
    """Processa intent order_build do LLM (múltiplos itens)."""
    return process_llm_add_item(phone, items, order_entities)


def process_llm_address(phone: str, address: dict, address_resolution: dict) -> JsonResponse:
    """Processa intent provide_address do LLM."""
    state = get_conversation_state(phone)

    # Se já tem match de bairro
    if address_resolution and address_resolution.get('matched_neighborhood'):
        neighborhood = address_resolution['matched_neighborhood']
        fee = address_resolution.get('delivery_fee', 0)

        full_address = f"{address.get('address_line', '')} {address.get('number', '')}".strip()
        if address.get('complement'):
            full_address += f", {address.get('complement')}"

        set_conversation_state(phone, "confirming_delivery", {
            "address": full_address,
            "neighborhood": neighborhood,
            "delivery_fee": float(fee)
        })

        # Busca itens do pedido
        items = state.get("data", {}).get("items", [])
        summary = format_order_summary(items, Decimal(str(fee)), 'DELIVERY')

        response = f"Endereço: *{full_address}*\nBairro: *{neighborhood}*\nTaxa: *R$ {fee:.2f}*\n\n{summary}\n\nConfirma o pedido?\n1️⃣ Sim\n2️⃣ Não"
        send_whatsapp_message(phone, response)
        return JsonResponse({"status": "ok", "action": "address_confirmed"})

    # Se não tem match, pede confirmação
    response = "Por favor, confirme o bairro para calcular a taxa de entrega."
    send_whatsapp_message(phone, response)
    return JsonResponse({"status": "ok", "action": "address_needs_neighborhood"})


def process_llm_payment(phone: str, payment_method: str, change_for: float = None) -> JsonResponse:
    """Processa intent choose_payment do LLM."""
    state = get_conversation_state(phone)

    payment_map = {
        'pix': 'PIX',
        'cash': 'CASH',
        'credit': 'CREDIT',
        'debit': 'DEBIT',
        'card': 'CREDIT'
    }

    method = payment_map.get(payment_method.lower(), 'PIX')

    set_conversation_state(phone, state.get('state', 'welcome'), {
        "payment_method": method,
        "change_for": change_for
    })

    # Redireciona para handler apropriado
    return process_standard_message(phone, payment_method, 'chat')


def process_llm_change(phone: str, change_for: float) -> JsonResponse:
    """Processa intent provide_change do LLM."""
    state = get_conversation_state(phone)

    set_conversation_state(phone, state.get('state', 'welcome'), {
        "change_for": float(change_for)
    })

    return process_standard_message(phone, str(int(change_for)), 'chat')


@csrf_exempt
def bot_webhook(request):
    """Webhook principal para receber mensagens do WAHA ou do n8n."""
    if request.method != 'POST':
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # NOVO: Detecta envelope do n8n
    if data.get('source') == 'n8n':
        logger.info("[N8N] Recebido envelope do n8n")
        return process_n8n_envelope(data)

    event = data.get('event')

    # Ignora eventos que não são mensagens novas
    # 'message' = mensagem nova, 'message.any' pode incluir sincronização
    if event not in ['message', 'message.any']:
        return JsonResponse({"status": "ignored", "reason": f"event_{event}"})

    # PERÍODO DE GRAÇA: Ignora TODAS as mensagens nos primeiros 60 segundos após iniciar
    # Isso evita disparo em massa quando WAHA sincroniza após deploy
    elapsed_since_start = time.time() - SERVICE_START_TIME
    if elapsed_since_start < STARTUP_GRACE_PERIOD:
        logger.warning(f"Mensagem ignorada - período de graça ({elapsed_since_start:.1f}s < {STARTUP_GRACE_PERIOD}s)")
        return JsonResponse({"status": "ignored", "reason": "startup_grace_period"})

    # Se for message.any, verifica se é mensagem realmente nova
    if event == 'message.any':
        logger.info("Evento message.any recebido - verificando se é mensagem nova")

    payload = data.get('payload', {})

    # Ignora se for mensagem de status/broadcast do WhatsApp
    if payload.get('isStatus') or payload.get('broadcast'):
        return JsonResponse({"status": "ignored", "reason": "status_or_broadcast"})

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

    # Verifica se o chatbot está ativo
    settings_obj = BusinessSettings.get_settings()
    if not settings_obj.chatbot_enabled:
        logger.info("Chatbot desativado - mensagem ignorada")
        return JsonResponse({"status": "ignored", "reason": "chatbot_disabled"})

    # IMPORTANTE: Ignora mensagens antigas para evitar disparo em massa ao reconectar
    current_time = int(time.time())

    # Tenta múltiplos campos de timestamp (WAHA usa diferentes formatos)
    timestamp = payload.get('timestamp')
    if not timestamp:
        # Tenta outros campos possíveis
        timestamp = payload.get('t')
        if not timestamp:
            _data = payload.get('_data', {})
            timestamp = _data.get('t') or _data.get('timestamp')

    if timestamp:
        try:
            ts = int(timestamp)
            # Se timestamp está em milissegundos, converte para segundos
            if ts > 9999999999:
                ts = ts // 1000
            message_age = current_time - ts
            if message_age > 60:  # Ignora mensagens com mais de 60 segundos
                logger.info(f"Mensagem antiga ignorada: {message_age}s atrás (ts={timestamp})")
                return JsonResponse({"status": "ignored", "reason": "old_message"})
        except (ValueError, TypeError) as e:
            logger.warning(f"Erro ao processar timestamp: {e}")
    else:
        # SEM TIMESTAMP: provavelmente é sincronização - ignora por segurança
        logger.warning(f"Mensagem sem timestamp - ignorando por segurança (possível sync)")
        return JsonResponse({"status": "ignored", "reason": "no_timestamp"})

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

    # Verifica também no _data.Type para pegar o tipo real da mídia
    _data = payload.get('_data', {})
    media_type = _data.get('Type', '')

    # Se o tipo no _data indica áudio, usa ele
    if media_type and media_type.lower() in ['ptt', 'audio', 'voice']:
        msg_type = media_type.lower()

    logger.info(f"DEBUG TIPO: msg_type={msg_type}, media_type={media_type}, hasMedia={payload.get('hasMedia')}")

    media_url = None
    if msg_type == 'image' or payload.get('hasMedia') or payload.get('media'):
        # Tenta várias formas de obter a URL da mídia
        media = payload.get('media', {})

        # Formato 1: media.url
        media_url = media.get('url') if media else None

        # Formato 2: mediaUrl direto no payload
        if not media_url:
            media_url = payload.get('mediaUrl')

        # Formato 3: _data.media.url
        if not media_url:
            _data = payload.get('_data', {})
            _media = _data.get('media', {})
            media_url = _media.get('url') if _media else None

        # Formato 4: media.link
        if not media_url and media:
            media_url = media.get('link')

        logger.info(f"MÍDIA DETECTADA - tipo: {msg_type}, hasMedia: {payload.get('hasMedia')}, media_url: {media_url}")
        logger.info(f"PAYLOAD COMPLETO DA MÍDIA: {json.dumps(payload, default=str)[:500]}")

    # Extrai nome do cliente se disponível
    _data = payload.get('_data', {})
    info = _data.get('Info', {})
    push_name = info.get('PushName', '')

    if push_name:
        get_or_create_customer(phone, push_name)

    state = get_conversation_state(phone)
    current_state = state.get("state", "welcome")

    logger.info(f"Mensagem de {phone}: {body[:50]}... (estado: {current_state})")

    # Verifica se é mensagem de áudio em qualquer estado
    audio_types = ['ptt', 'audio', 'voice', 'audio_message']
    if msg_type in audio_types or media_type.lower() in audio_types:
        logger.info(f"ÁUDIO DETECTADO - msg_type={msg_type}, media_type={media_type}")
        response = (
            f"Oi! Infelizmente não consigo ouvir áudios 😅\n\n"
            f"Mas você pode ligar pra gente:\n"
            f"📞 *{CONTACT_PHONE}*\n\n"
            f"Ou se preferir, pode digitar seu pedido aqui mesmo! 🍕"
        )
        send_whatsapp_message(phone, response)
        return JsonResponse({"status": "ok"})

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

    elif current_state == "awaiting_promo_more_items":
        response = handle_promo_more_items(phone, body)

    elif current_state == "awaiting_promo_another_item":
        response = handle_promo_another_item(phone, body)

    elif current_state == "awaiting_promo_order_type":
        response = handle_promo_order_type(phone, body)

    elif current_state == "awaiting_more_promo":
        response = handle_more_promo(phone, body)

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

    elif current_state == "awaiting_payment_choice":
        response = handle_payment_choice(phone, body)

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

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db.models import Sum, Count, Avg
from django.utils import timezone
from datetime import timedelta
import json

from .models import Order, Product, DeliveryFee, BusinessSettings, Customer
from .waha_service import send_whatsapp_message


def login_view(request):
    """View de login."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('dashboard')
        else:
            messages.error(request, 'Usuario ou senha invalidos')

    return render(request, 'login.html')


def logout_view(request):
    """View de logout."""
    logout(request)
    return redirect('login')


@login_required
def dashboard_view(request):
    """Dashboard principal com Kanban de pedidos."""
    new_orders = Order.objects.filter(status='NEW').select_related('customer').prefetch_related('items__product')
    awaiting_payment = Order.objects.filter(status='AWAITING_PAYMENT').select_related('customer').prefetch_related('items__product')
    preparing = Order.objects.filter(status='PREPARING').select_related('customer').prefetch_related('items__product')
    out_delivery = Order.objects.filter(status__in=['OUT_FOR_DELIVERY', 'READY_FOR_PICKUP']).select_related('customer').prefetch_related('items__product')

    context = {
        'new_orders': new_orders,
        'awaiting_payment': awaiting_payment,
        'preparing': preparing,
        'out_delivery': out_delivery,
        'page_title': 'Pedidos',
    }
    return render(request, 'dashboard.html', context)


@login_required
def payments_view(request):
    """Tela de gerenciamento de comprovantes."""
    orders_with_receipt = Order.objects.filter(
        payment_status='RECEIPT_RECEIVED'
    ).select_related('customer').prefetch_related('items__product')

    context = {
        'orders': orders_with_receipt,
        'page_title': 'Comprovantes',
    }
    return render(request, 'payments.html', context)


@login_required
def menu_view(request):
    """Tela de cardapio e promocoes."""
    if request.method == 'POST':
        settings_obj = BusinessSettings.get_settings()

        if 'menu_image' in request.FILES:
            settings_obj.menu_image = request.FILES['menu_image']

        if 'promo_image' in request.FILES:
            settings_obj.promo_image = request.FILES['promo_image']

        settings_obj.promo_text = request.POST.get('promo_text', '')
        settings_obj.promo_active = request.POST.get('promo_active') == 'on'
        settings_obj.save()

        messages.success(request, 'Cardapio e promocoes atualizados!')
        return redirect('menu')

    products = Product.objects.all().order_by('category', 'name')
    settings_obj = BusinessSettings.get_settings()

    context = {
        'products': products,
        'settings': settings_obj,
        'page_title': 'Cardapio e Promocoes',
    }
    return render(request, 'menu.html', context)


@login_required
def delivery_fees_view(request):
    """Tela de taxas de entrega por bairro."""
    if request.method == 'POST':
        action = request.POST.get('action')

        try:
            if action == 'create':
                neighborhood = request.POST.get('neighborhood', '').strip()
                fee_value = request.POST.get('fee', '0').replace(',', '.')
                estimated_time = request.POST.get('estimated_time', '60')

                if not neighborhood:
                    messages.error(request, 'Nome do bairro é obrigatório!')
                    return redirect('delivery_fees')

                DeliveryFee.objects.create(
                    neighborhood=neighborhood,
                    fee=float(fee_value) if fee_value else 0,
                    estimated_time=int(estimated_time) if estimated_time else 60,
                    active=request.POST.get('active') == 'on'
                )
                messages.success(request, 'Taxa de entrega criada!')

            elif action == 'update':
                fee_id = request.POST.get('fee_id')
                fee_obj = get_object_or_404(DeliveryFee, id=fee_id)
                fee_value = request.POST.get('fee', '0').replace(',', '.')
                estimated_time = request.POST.get('estimated_time', '60')

                fee_obj.neighborhood = request.POST.get('neighborhood', fee_obj.neighborhood)
                fee_obj.fee = float(fee_value) if fee_value else 0
                fee_obj.estimated_time = int(estimated_time) if estimated_time else 60
                fee_obj.active = request.POST.get('active') == 'on'
                fee_obj.save()
                messages.success(request, 'Taxa de entrega atualizada!')

            elif action == 'delete':
                fee_id = request.POST.get('fee_id')
                DeliveryFee.objects.filter(id=fee_id).delete()
                messages.success(request, 'Taxa de entrega removida!')

        except ValueError as e:
            messages.error(request, f'Valor inválido: {e}')
        except Exception as e:
            messages.error(request, f'Erro ao salvar: {e}')

        return redirect('delivery_fees')

    fees = DeliveryFee.objects.all().order_by('neighborhood')

    context = {
        'fees': fees,
        'page_title': 'Taxas de Entrega',
    }
    return render(request, 'delivery_fees.html', context)


@login_required
def settings_view(request):
    """Tela de configuracoes do negocio."""
    settings_obj = BusinessSettings.get_settings()

    if request.method == 'POST':
        settings_obj.business_name = request.POST.get('business_name', settings_obj.business_name)
        settings_obj.pix_key = request.POST.get('pix_key', settings_obj.pix_key)
        settings_obj.pix_name = request.POST.get('pix_name', settings_obj.pix_name)
        settings_obj.opening_time = request.POST.get('opening_time', settings_obj.opening_time)
        settings_obj.closing_time = request.POST.get('closing_time', settings_obj.closing_time)
        settings_obj.min_delivery_time = request.POST.get('min_delivery_time', settings_obj.min_delivery_time)
        settings_obj.max_delivery_time = request.POST.get('max_delivery_time', settings_obj.max_delivery_time)
        settings_obj.save()

        messages.success(request, 'Configuracoes salvas!')
        return redirect('settings')

    context = {
        'settings': settings_obj,
        'page_title': 'Configuracoes',
    }
    return render(request, 'settings.html', context)


@login_required
def reports_view(request):
    """Tela de relatorios."""
    period = request.GET.get('period', 'today')
    today = timezone.now().date()

    if period == 'today':
        start_date = end_date = today
    elif period == 'week':
        start_date = today - timedelta(days=7)
        end_date = today
    elif period == 'month':
        start_date = today - timedelta(days=30)
        end_date = today
    else:
        start_date = request.GET.get('date_from', today)
        end_date = request.GET.get('date_to', today)

    orders = Order.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date
    )

    completed = orders.exclude(status='CANCELLED')
    cancelled = orders.filter(status='CANCELLED')

    total_orders = orders.count()
    total_revenue = completed.aggregate(total=Sum('total'))['total'] or 0
    average_ticket = completed.aggregate(avg=Avg('total'))['avg'] or 0
    cancelled_count = cancelled.count()
    cancellation_rate = (cancelled_count / total_orders * 100) if total_orders > 0 else 0

    from .models import OrderItem
    from django.db.models import F

    top_products = OrderItem.objects.filter(
        order__created_at__date__gte=start_date,
        order__created_at__date__lte=end_date,
        order__status__in=['COMPLETED', 'OUT_FOR_DELIVERY', 'READY_FOR_PICKUP', 'PREPARING']
    ).values(
        product_name=F('product__name')
    ).annotate(
        total_sold=Sum('quantity'),
        total_revenue=Sum(F('quantity') * F('unit_price'))
    ).order_by('-total_sold')[:10]

    from django.db.models.functions import ExtractHour

    hourly_data = completed.annotate(
        hour=ExtractHour('created_at')
    ).values('hour').annotate(
        count=Count('id')
    ).order_by('hour')

    neighborhood_data = completed.filter(
        order_type='DELIVERY'
    ).values('neighborhood').annotate(
        count=Count('id'),
        revenue=Sum('total')
    ).order_by('-count')[:10]

    context = {
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'average_ticket': average_ticket,
        'cancelled_count': cancelled_count,
        'cancellation_rate': cancellation_rate,
        'top_products': list(top_products),
        'hourly_data': list(hourly_data),
        'neighborhood_data': list(neighborhood_data),
        'period': period,
        'start_date': start_date,
        'end_date': end_date,
        'page_title': 'Relatorios',
    }
    return render(request, 'reports.html', context)


@login_required
@require_POST
def update_order_status(request):
    """Atualiza status do pedido via AJAX."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON invalido'}, status=400)

    order_id = data.get('order_id')
    new_status = data.get('status')

    order = get_object_or_404(Order, id=order_id)
    old_status = order.status
    order.status = new_status
    order.save()

    settings_obj = BusinessSettings.get_settings()

    if new_status == 'OUT_FOR_DELIVERY' and old_status != 'OUT_FOR_DELIVERY':
        message = (
            f"Boa noite, seu pedido esta a caminho! "
            f"Ao chegar, nos notifique, por gentileza, se chegou tudo direitinho. "
            f"E de suma importancia para o nosso crescimento com voces.\n"
            f"A {settings_obj.business_name} agradece pela preferencia"
        )
        send_whatsapp_message(order.customer.phone, message)

    elif new_status == 'READY_FOR_PICKUP' and old_status != 'READY_FOR_PICKUP':
        message = (
            f"Boa noite, seu pedido esta pronto para retirada!\n"
            f"A {settings_obj.business_name} agradece pela preferencia"
        )
        send_whatsapp_message(order.customer.phone, message)

    return JsonResponse({
        'status': 'ok',
        'order_id': order.id,
        'new_status': order.status,
        'status_display': order.get_status_display()
    })


@login_required
@require_POST
def confirm_payment(request):
    """Confirma pagamento do pedido."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON invalido'}, status=400)

    order_id = data.get('order_id')
    order = get_object_or_404(Order, id=order_id)

    order.payment_status = 'CONFIRMED'
    order.status = 'PREPARING'
    order.save()

    # Notifica o cliente que o pagamento foi confirmado
    settings = BusinessSettings.get_settings()
    message = (
        f"Pagamento confirmado! ✅\n\n"
        f"Seu pedido já está sendo preparado! 🍕👨‍🍳\n\n"
        f"⏱️ Previsão de entrega: {settings.min_delivery_time} a {settings.max_delivery_time} minutos\n\n"
        f"Quando sair pra entrega eu te aviso aqui!\n\n"
        f"A {settings.business_name} agradece! ❤️"
    )
    send_whatsapp_message(order.customer.phone, message)

    return JsonResponse({
        'status': 'ok',
        'order_id': order.id,
        'payment_status': order.payment_status
    })


@login_required
@require_POST
def reject_payment(request):
    """Rejeita comprovante de pagamento."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON invalido'}, status=400)

    order_id = data.get('order_id')
    if not order_id:
        return JsonResponse({'error': 'order_id obrigatorio'}, status=400)

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Pedido nao encontrado'}, status=404)

    order.payment_status = 'PENDING'
    order.save()

    # Restaura o estado da conversa para aguardar novo comprovante
    try:
        from django.core.cache import cache
        phone = order.customer.phone
        key = f"conversation:{phone}"
        state = {
            "state": "awaiting_receipt",
            "data": {"order_id": order.id},
            "history": []
        }
        cache.set(key, json.dumps(state), 3600)  # 1 hora
    except Exception as e:
        print(f"Erro ao restaurar estado: {e}")

    # Envia mensagem ao cliente
    try:
        settings = BusinessSettings.get_settings()
        message = (
            f"Opa! 😅 Não conseguimos verificar o comprovante enviado.\n\n"
            f"Pode mandar novamente a foto do comprovante do PIX?\n\n"
            f"Chave PIX: *{settings.pix_key}*\n"
            f"Nome: {settings.pix_name}\n\n"
            f"_Ou digite 'pagar na entrega' se preferir_"
        )
        send_whatsapp_message(order.customer.phone, message)
    except Exception as e:
        print(f"Erro ao enviar mensagem: {e}")

    return JsonResponse({
        'status': 'ok',
        'order_id': order.id
    })


@login_required
def order_counts(request):
    """Retorna contagem de pedidos por status para polling."""
    from django.utils import timezone
    today = timezone.now().date()

    counts = {
        'new': Order.objects.filter(status='NEW', created_at__date=today).count(),
        'awaiting_payment': Order.objects.filter(status='AWAITING_PAYMENT', created_at__date=today).count(),
        'preparing': Order.objects.filter(status='PREPARING', created_at__date=today).count(),
        'out_delivery': Order.objects.filter(
            status__in=['OUT_FOR_DELIVERY', 'READY_FOR_PICKUP'],
            created_at__date=today
        ).count(),
    }
    return JsonResponse(counts)


@login_required
@require_POST
def product_action(request):
    """Acoes CRUD para produtos."""
    action = request.POST.get('action')

    if action == 'create':
        product = Product.objects.create(
            name=request.POST.get('name'),
            description=request.POST.get('description', ''),
            price=request.POST.get('price'),
            category=request.POST.get('category'),
            active=request.POST.get('active') == 'on'
        )
        if 'image' in request.FILES:
            product.image = request.FILES['image']
            product.save()
        messages.success(request, 'Produto criado!')

    elif action == 'update':
        product_id = request.POST.get('product_id')
        product = get_object_or_404(Product, id=product_id)
        product.name = request.POST.get('name')
        product.description = request.POST.get('description', '')
        product.price = request.POST.get('price')
        product.category = request.POST.get('category')
        product.active = request.POST.get('active') == 'on'
        if 'image' in request.FILES:
            product.image = request.FILES['image']
        product.save()
        messages.success(request, 'Produto atualizado!')

    elif action == 'delete':
        product_id = request.POST.get('product_id')
        Product.objects.filter(id=product_id).delete()
        messages.success(request, 'Produto removido!')

    return redirect('menu')

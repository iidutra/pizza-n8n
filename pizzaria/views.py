from django.db.models import Sum, Count, Avg, F
from django.db.models.functions import ExtractHour
from django.utils import timezone
from django.http import JsonResponse
from datetime import timedelta
from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework.views import APIView


def health_check(request):
    """Endpoint de health check para o Railway."""
    return JsonResponse({'status': 'ok'})

from .models import Customer, Product, DeliveryFee, Order, OrderItem, BusinessSettings
from .serializers import (
    CustomerSerializer, ProductSerializer, DeliveryFeeSerializer,
    OrderSerializer, OrderCreateSerializer, BusinessSettingsSerializer,
    ReportSummarySerializer, TopProductSerializer, HourlyReportSerializer,
    NeighborhoodReportSerializer
)
from .waha_service import send_whatsapp_message


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    filterset_fields = ['phone', 'neighborhood']
    search_fields = ['name', 'phone', 'address']


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    filterset_fields = ['category', 'active']
    search_fields = ['name', 'description']

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == 'list':
            active_only = self.request.query_params.get('active_only', 'false')
            if active_only.lower() == 'true':
                queryset = queryset.filter(active=True)
        return queryset


class DeliveryFeeViewSet(viewsets.ModelViewSet):
    queryset = DeliveryFee.objects.all()
    serializer_class = DeliveryFeeSerializer
    filterset_fields = ['active']
    search_fields = ['neighborhood']


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all().select_related('customer').prefetch_related('items__product')
    filterset_fields = ['status', 'order_type', 'payment_status', 'neighborhood']
    search_fields = ['customer__name', 'customer__phone', 'delivery_address']

    def get_serializer_class(self):
        if self.action == 'create':
            return OrderCreateSerializer
        return OrderSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        status_param = self.request.query_params.get('status')
        if status_param:
            statuses = status_param.split(',')
            queryset = queryset.filter(status__in=statuses)

        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)

        date_to = self.request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        return queryset

    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        order = self.get_object()
        new_status = request.data.get('status')

        if new_status not in dict(Order.STATUS_CHOICES):
            return Response(
                {'error': 'Status invalido'},
                status=status.HTTP_400_BAD_REQUEST
            )

        old_status = order.status
        order.status = new_status
        order.save()

        if new_status == 'OUT_FOR_DELIVERY' and old_status != 'OUT_FOR_DELIVERY':
            settings = BusinessSettings.get_settings()
            message = (
                f"Boa noite, seu pedido esta a caminho! "
                f"Ao chegar, nos notifique, por gentileza, se chegou tudo direitinho. "
                f"E de suma importancia para o nosso crescimento com voces.\n"
                f"A {settings.business_name} agradece pela preferencia"
            )
            send_whatsapp_message(order.customer.phone, message)

        elif new_status == 'READY_FOR_PICKUP' and old_status != 'READY_FOR_PICKUP':
            settings = BusinessSettings.get_settings()
            message = (
                f"Boa noite, seu pedido esta pronto para retirada!\n"
                f"A {settings.business_name} agradece pela preferencia"
            )
            send_whatsapp_message(order.customer.phone, message)

        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=['post'])
    def confirm_payment(self, request, pk=None):
        order = self.get_object()
        order.payment_status = 'CONFIRMED'
        order.status = 'PREPARING'
        order.save()
        return Response(OrderSerializer(order).data)

    @action(detail=True, methods=['post'])
    def reject_payment(self, request, pk=None):
        order = self.get_object()
        order.payment_status = 'PENDING'
        order.save()

        message = (
            "Houve um problema com o comprovante enviado. "
            "Por favor, envie novamente o comprovante de pagamento."
        )
        send_whatsapp_message(order.customer.phone, message)

        return Response(OrderSerializer(order).data)


class BusinessSettingsView(APIView):
    def get(self, request):
        settings = BusinessSettings.get_settings()
        serializer = BusinessSettingsSerializer(settings)
        return Response(serializer.data)

    def patch(self, request):
        settings = BusinessSettings.get_settings()
        serializer = BusinessSettingsSerializer(settings, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ReportSummaryView(APIView):
    def get(self, request):
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        period = request.query_params.get('period', 'today')

        today = timezone.now().date()

        if date_from and date_to:
            start_date = date_from
            end_date = date_to
        elif period == 'today':
            start_date = end_date = today
        elif period == 'week':
            start_date = today - timedelta(days=7)
            end_date = today
        elif period == 'month':
            start_date = today - timedelta(days=30)
            end_date = today
        else:
            start_date = end_date = today

        orders = Order.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date
        )

        completed_orders = orders.exclude(status='CANCELLED')
        cancelled_orders = orders.filter(status='CANCELLED')

        total_orders = orders.count()
        total_revenue = completed_orders.aggregate(total=Sum('total'))['total'] or 0
        average_ticket = completed_orders.aggregate(avg=Avg('total'))['avg'] or 0
        cancelled_count = cancelled_orders.count()
        cancellation_rate = (cancelled_count / total_orders * 100) if total_orders > 0 else 0

        delivery_orders = completed_orders.filter(order_type='DELIVERY').count()
        pickup_orders = completed_orders.filter(order_type='PICKUP').count()

        data = {
            'total_orders': total_orders,
            'total_revenue': total_revenue,
            'average_ticket': average_ticket,
            'cancelled_orders': cancelled_count,
            'cancellation_rate': cancellation_rate,
            'delivery_orders': delivery_orders,
            'pickup_orders': pickup_orders,
        }

        serializer = ReportSummarySerializer(data)
        return Response(serializer.data)


class TopProductsView(APIView):
    def get(self, request):
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        limit = int(request.query_params.get('limit', 10))

        queryset = OrderItem.objects.filter(
            order__status__in=['COMPLETED', 'OUT_FOR_DELIVERY', 'READY_FOR_PICKUP', 'PREPARING']
        )

        if date_from:
            queryset = queryset.filter(order__created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(order__created_at__date__lte=date_to)

        top_products = queryset.values(
            product_name=F('product__name')
        ).annotate(
            total_sold=Sum('quantity'),
            total_revenue=Sum(F('quantity') * F('unit_price'))
        ).order_by('-total_sold')[:limit]

        serializer = TopProductSerializer(top_products, many=True)
        return Response(serializer.data)


class HourlyReportView(APIView):
    def get(self, request):
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        queryset = Order.objects.exclude(status='CANCELLED')

        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        hourly_data = queryset.annotate(
            hour=ExtractHour('created_at')
        ).values('hour').annotate(
            orders_count=Count('id')
        ).order_by('hour')

        serializer = HourlyReportSerializer(hourly_data, many=True)
        return Response(serializer.data)


class NeighborhoodReportView(APIView):
    def get(self, request):
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        queryset = Order.objects.filter(
            order_type='DELIVERY'
        ).exclude(status='CANCELLED')

        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        neighborhood_data = queryset.values('neighborhood').annotate(
            orders_count=Count('id'),
            total_revenue=Sum('total')
        ).order_by('-orders_count')

        serializer = NeighborhoodReportSerializer(neighborhood_data, many=True)
        return Response(serializer.data)

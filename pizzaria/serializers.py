from rest_framework import serializers
from .models import Customer, Product, DeliveryFee, Order, OrderItem, BusinessSettings


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = '__all__'


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = '__all__'


class DeliveryFeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryFee
        fields = '__all__'


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'quantity', 'unit_price', 'notes', 'total_price']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    customer_phone = serializers.CharField(source='customer.phone', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    order_type_display = serializers.CharField(source='get_order_type_display', read_only=True)
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'customer', 'customer_name', 'customer_phone',
            'status', 'status_display', 'order_type', 'order_type_display',
            'delivery_address', 'neighborhood', 'delivery_fee',
            'subtotal', 'total', 'payment_status', 'payment_status_display',
            'payment_receipt', 'notes', 'items', 'created_at', 'updated_at'
        ]


class OrderCreateSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)

    class Meta:
        model = Order
        fields = [
            'customer', 'order_type', 'delivery_address', 'neighborhood',
            'delivery_fee', 'notes', 'items'
        ]

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        order = Order.objects.create(**validated_data)

        for item_data in items_data:
            OrderItem.objects.create(order=order, **item_data)

        order.calculate_totals()
        order.save()
        return order


class BusinessSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessSettings
        fields = '__all__'


class ReportSummarySerializer(serializers.Serializer):
    total_orders = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)
    average_ticket = serializers.DecimalField(max_digits=10, decimal_places=2)
    cancelled_orders = serializers.IntegerField()
    cancellation_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    delivery_orders = serializers.IntegerField()
    pickup_orders = serializers.IntegerField()


class TopProductSerializer(serializers.Serializer):
    product_name = serializers.CharField()
    total_sold = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)


class HourlyReportSerializer(serializers.Serializer):
    hour = serializers.IntegerField()
    orders_count = serializers.IntegerField()


class NeighborhoodReportSerializer(serializers.Serializer):
    neighborhood = serializers.CharField()
    orders_count = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=12, decimal_places=2)

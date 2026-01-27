from django.contrib import admin
from .models import Customer, Product, DeliveryFee, Order, OrderItem, BusinessSettings


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'neighborhood', 'created_at']
    search_fields = ['name', 'phone', 'address']
    list_filter = ['neighborhood', 'created_at']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price', 'active']
    list_filter = ['category', 'active']
    search_fields = ['name', 'description']
    list_editable = ['price', 'active']


@admin.register(DeliveryFee)
class DeliveryFeeAdmin(admin.ModelAdmin):
    list_display = ['neighborhood', 'fee', 'estimated_time', 'active']
    list_editable = ['fee', 'estimated_time', 'active']
    search_fields = ['neighborhood']


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['total_price']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'customer', 'status', 'order_type', 'total', 'payment_status', 'created_at']
    list_filter = ['status', 'order_type', 'payment_status', 'created_at']
    search_fields = ['customer__name', 'customer__phone', 'delivery_address']
    readonly_fields = ['subtotal', 'total', 'created_at', 'updated_at']
    inlines = [OrderItemInline]
    date_hierarchy = 'created_at'


@admin.register(BusinessSettings)
class BusinessSettingsAdmin(admin.ModelAdmin):
    list_display = ['business_name', 'pix_key', 'opening_time', 'closing_time', 'promo_active']

    def has_add_permission(self, request):
        return not BusinessSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

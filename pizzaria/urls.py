from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views, bot_views, panel_views

router = DefaultRouter()
router.register(r'customers', views.CustomerViewSet)
router.register(r'products', views.ProductViewSet)
router.register(r'delivery-fees', views.DeliveryFeeViewSet)
router.register(r'orders', views.OrderViewSet)

urlpatterns = [
    # Health check
    path('api/health/', views.health_check, name='health_check'),

    # API REST
    path('api/', include(router.urls)),
    path('api/settings/', views.BusinessSettingsView.as_view(), name='api_settings'),
    path('api/reports/summary/', views.ReportSummaryView.as_view(), name='api_report_summary'),
    path('api/reports/top-products/', views.TopProductsView.as_view(), name='api_top_products'),
    path('api/reports/hourly/', views.HourlyReportView.as_view(), name='api_hourly_report'),
    path('api/reports/neighborhoods/', views.NeighborhoodReportView.as_view(), name='api_neighborhood_report'),

    # Bot Webhook (com e sem barra final)
    path('api/bot/message/', bot_views.bot_webhook, name='bot_webhook'),
    path('api/bot/message', bot_views.bot_webhook, name='bot_webhook_no_slash'),
    path('api/bot/send-status/', bot_views.send_status_update, name='send_status_update'),
    path('api/bot/send-status', bot_views.send_status_update, name='send_status_update_no_slash'),
    path('api/bot/debug/', bot_views.debug_waha, name='debug_waha'),

    # Dashboard
    path('', panel_views.dashboard_view, name='dashboard'),
    path('dashboard/', panel_views.dashboard_view, name='dashboard_alt'),
    path('login/', panel_views.login_view, name='login'),
    path('logout/', panel_views.logout_view, name='logout'),
    path('payments/', panel_views.payments_view, name='payments'),
    path('menu/', panel_views.menu_view, name='menu'),
    path('delivery-fees/', panel_views.delivery_fees_view, name='delivery_fees'),
    path('settings/', panel_views.settings_view, name='settings'),
    path('reports/', panel_views.reports_view, name='reports'),

    # AJAX Actions
    path('ajax/update-order-status/', panel_views.update_order_status, name='update_order_status'),
    path('ajax/confirm-payment/', panel_views.confirm_payment, name='confirm_payment'),
    path('ajax/reject-payment/', panel_views.reject_payment, name='reject_payment'),
    path('ajax/product-action/', panel_views.product_action, name='product_action'),
]

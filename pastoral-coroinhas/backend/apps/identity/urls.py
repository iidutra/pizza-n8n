from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.identity.views import (
    LoginFamiliaView,
    LoginStaffView,
    LoginView,
    MeView,
    RecuperarSenhaView,
    TrocarSenhaView,
)

urlpatterns = [
    path("login", LoginView.as_view(), name="login"),
    path("login/familia", LoginFamiliaView.as_view(), name="login-familia"),
    path("login/staff", LoginStaffView.as_view(), name="login-staff"),
    path("recuperar-senha", RecuperarSenhaView.as_view(), name="recuperar-senha"),
    path("trocar-senha", TrocarSenhaView.as_view(), name="trocar-senha"),
    path("refresh", TokenRefreshView.as_view(), name="token-refresh"),
    path("me", MeView.as_view(), name="me"),
]

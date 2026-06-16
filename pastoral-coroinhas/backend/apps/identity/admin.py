from django.contrib import admin

from .models import TipoPerfil, Usuario


@admin.register(Usuario)
class UsuarioAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo_perfil", "email", "cpf", "is_active", "must_change_password")
    list_filter = ("tipo_perfil", "is_active")
    search_fields = ("nome", "email", "cpf")
    readonly_fields = ("criado_em", "atualizado_em")

    fieldsets = (
        (None, {"fields": ("nome", "tipo_perfil", "email", "cpf", "password")}),
        ("Vínculos", {"fields": ("coroinha", "responsavel")}),
        ("Status", {"fields": ("must_change_password", "is_active", "is_staff", "is_superuser")}),
        ("Datas", {"fields": ("criado_em", "atualizado_em")}),
    )

    def save_model(self, request, obj, form, change):
        if not change and obj.tipo_perfil == TipoPerfil.COORDENADOR:
            obj.is_staff = True
        super().save_model(request, obj, form, change)

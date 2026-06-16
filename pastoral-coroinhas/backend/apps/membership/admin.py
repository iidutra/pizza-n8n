from django.contrib import admin

from .models import Coroinha, Inscricao, Responsavel


@admin.register(Responsavel)
class ResponsavelAdmin(admin.ModelAdmin):
    list_display = ("nome", "cpf", "telefone", "email")
    search_fields = ("nome", "cpf", "email")


@admin.register(Coroinha)
class CoroinhaAdmin(admin.ModelAdmin):
    list_display = ("nome", "idade", "turma", "status", "data_nascimento")
    list_filter = ("turma", "status")
    search_fields = ("nome", "cpf")
    filter_horizontal = ("responsaveis",)


@admin.register(Inscricao)
class InscricaoAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "criado_em", "aprovado_em")
    list_filter = ("status",)

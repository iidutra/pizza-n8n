from rest_framework.permissions import BasePermission

from apps.identity.models import TipoPerfil


class IsCoordenador(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.tipo_perfil == TipoPerfil.COORDENADOR
        )


class IsGestorCoroinhas(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.tipo_perfil in (
            TipoPerfil.COORDENADOR,
            TipoPerfil.SECRETARIO,
        )


class IsStaffPastoral(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_staff_pastoral


class IsFamilia(BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.is_familia

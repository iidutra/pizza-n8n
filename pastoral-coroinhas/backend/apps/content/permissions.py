from rest_framework.permissions import BasePermission

from apps.identity.models import TipoPerfil


class IsFamiliaOuStaff(BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.user.is_familia or request.user.is_staff_pastoral

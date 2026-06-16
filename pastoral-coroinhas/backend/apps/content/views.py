from rest_framework import viewsets

from apps.content.models import Documento, Noticia
from apps.content.serializers import DocumentoSerializer, NoticiaSerializer
from apps.content.permissions import IsFamiliaOuStaff
from apps.identity.permissions import IsGestorCoroinhas, IsStaffPastoral


class NoticiaViewSet(viewsets.ModelViewSet):
    queryset = Noticia.objects.filter(ativo=True)
    serializer_class = NoticiaSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsFamiliaOuStaff()]
        return [IsGestorCoroinhas()]

    def get_queryset(self):
        qs = Noticia.objects.all()
        user = self.request.user
        if user.is_authenticated and user.is_familia:
            return qs.filter(ativo=True)
        return qs

    def perform_create(self, serializer):
        if serializer.validated_data.get("destaque"):
            Noticia.objects.filter(destaque=True).update(destaque=False)
        serializer.save(autor=self.request.user)

    def perform_update(self, serializer):
        if serializer.validated_data.get("destaque"):
            Noticia.objects.filter(destaque=True).exclude(pk=self.get_object().pk).update(destaque=False)
        serializer.save()


class DocumentoViewSet(viewsets.ModelViewSet):
    queryset = Documento.objects.all()
    serializer_class = DocumentoSerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsFamiliaOuStaff()]
        return [IsGestorCoroinhas()]

    def get_queryset(self):
        user = self.request.user
        qs = Documento.objects.filter(ativo=True) if user.is_authenticated and user.is_familia else Documento.objects.all()
        categoria = self.request.query_params.get("categoria")
        if categoria:
            qs = qs.filter(categoria=categoria)
        return qs

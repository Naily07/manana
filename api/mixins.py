
from .permissions import *
from rest_framework.permissions import IsAuthenticated


class GestionnaireEditorMixin():
    permission_classes = [IsAuthenticated, IsGestionnaire]

class VendeurEditorMixin():
    permission_classes = [IsAuthenticated, IsVendeur]

class PropriosEditorMixin:
    permission_classes = [IsAuthenticated, IsProprio]


from datetime import timedelta
from django.utils import timezone
from rest_framework.generics import GenericAPIView
from stock.models import Product, Facture

class ProductQsField(GenericAPIView):
    # qs_expired = "expired"
    qs_field = "etat"
    def get_queryset(self):
        qs = super().get_queryset()
        try:
            etat = self.kwargs[self.qs_field]
            if etat == "expired":
                # print("exp")
                today = timezone.now().date()
                seven_months_from_now = today + timedelta(days=210)
                # print(seven_months_from_now)
                qs = Product.objects.filter(date_peremption__lte=seven_months_from_now, date_peremption__gte = timezone.now())
                return qs
            elif etat == "rupture" :
                # print("RUPTEE")
                qs = Product.objects.filter(qte_gros__lte = 50)
                return qs
        except Exception as e:
            # print(e)
            return qs   
    
class userFactureQs(GenericAPIView):
    
    def get_queryset(self):
        qs =  super().get_queryset()
        user = self.request.user
        userType = user.groups.filter(name = 'vendeurs').exists()
        if userType:
            data = {"owner" : user}
            return qs.filter(**data)
        return qs

class ProprioQueryset(GenericAPIView):

    def get_queryset(self):
        qs =  super().get_queryset()
        user = self.request.user
        userType = user.groups.filter(name = 'proprios').exists()
        if userType :
            # print("TYPE", userType)
            data = {"is_superuser" : False}
            # print(data)
            return qs.filter(**data)
        return qs
from django.shortcuts import render
from rest_framework import generics
from rest_framework.views import APIView
#Test deploy 
from api.paginations import StandardResultPageination
from api.mixins import GestionnaireEditorMixin, VendeurEditorMixin
from api.mixins import ProductQsField
from .models import *
from .serialiser import *
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError

from api.permissions import IsGestionnaire
from rest_framework.permissions import IsAuthenticated
from api.mixins import userFactureQs
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
# Create your views here.
class CreateDetail(generics.ListCreateAPIView): 
    queryset = Detail.objects.all()
    serializer_class = DetailSerialiser
    
class ListProduct(generics.ListAPIView, ProductQsField):
    queryset = Product.objects.all()
    serializer_class = ProductSerialiser
    # qs_field_expired = "expired"
    # qs_rupture = "rupture"
    permission_classes = [IsAuthenticated, ]

class CreateProduct(GestionnaireEditorMixin, generics.CreateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerialiser

class CreateBulkStock(GestionnaireEditorMixin, APIView):
    # permission_classes = [IsAuthenticated, IsGestionnaire]
    def post(self, request):
        productsToCreate = []
        productsToUpdate = []
        productList = request.data
        user = request.user
        addStockListInstance = []

        try:
            with transaction.atomic():
                for newProduct in productList:
                    if newProduct:
                        detail = newProduct.pop('detail')
                        marque = newProduct.pop('marque', None)
                        fournisseur = newProduct.pop('fournisseur')
                        print("Marque", marque)

                        detailInstance, createdD = Detail.objects.get_or_create(
                            designation=detail['designation'], 
                            famille=detail['famille'], 
                            classe=detail['classe'], 
                            type_gros=detail['type_gros'],
                        )
                        marqueInstance = None
                        if marque:
                            marqueInstance, createdM = Marque.objects.get_or_create(nom=marque)
                        fournisseurInstance, createdF = Fournisseur.objects.get_or_create(
                            nom=fournisseur['nom'].upper(),
                            defaults={
                                'adress': fournisseur.get('adress', ''),
                                'contact': fournisseur.get('contact', '')
                            }
                        )
                        productExist = Product.objects.filter(
                            detail=detailInstance, marque=marqueInstance, fournisseur=fournisseurInstance
                        ).first()

                        new_qte_gros = newProduct['qte_gros']
                        newProduct['qte_gros'] = new_qte_gros

                        if productExist: 
                            if int(newProduct['prix_gros']) and int(newProduct['prix_gros']) > 0:
                                productExist.prix_gros = int(newProduct['prix_gros'])
                            productExist.qte_gros += new_qte_gros

                            productsToUpdate.append(productExist)

                            addStockInstance = AjoutStock(
                                # qte_unit_transaction = newProduct['qte_unit'],
                                qte_gros_transaction = newProduct['qte_gros'],
                                # qte_detail_transaction = newProduct['qte_detail'],
                                type_transaction="Maj",
                                prix_gros = productExist.prix_gros,
                                # prix_unit = productExist.prix_unit,
                                # prix_detail = productExist.prix_detail,
                                prix_total = (int(productExist.prix_gros) * int( newProduct['qte_gros'])),
                                product=productExist,
                                gestionnaire=user
                            )
                            addStockListInstance.append(addStockInstance)
                        else:
                            if marque:
                                productsToCreate.append(Product(**newProduct, detail=detailInstance, marque=marqueInstance, fournisseur=fournisseurInstance)) 
                            else :
                                productsToCreate.append(Product(**newProduct, detail=detailInstance, fournisseur=fournisseurInstance)) 
                        

                if len(productsToUpdate) > 0:
                    Product.objects.bulk_update(productsToUpdate, fields=['prix_gros', 'qte_gros'])
                if len(productsToCreate) > 0:
                    for product in productsToCreate:
                        product.save()

                        addStockListInstance.append(
                            AjoutStock(
                                # qte_unit_transaction=product.qte_unit,
                                qte_gros_transaction=product.qte_gros,
                                # qte_detail_transaction=product.qte_detail,
                                type_transaction="Ajout",
                                prix_gros = product.prix_gros,
                                # prix_unit = product.prix_unit,
                                # prix_detail = product.prix_detail,
                                prix_total = (int(product.prix_gros) * int(product.qte_gros)), 
                                product=product,  
                                gestionnaire=user
                            )
                        )

                AjoutStock.objects.bulk_create(addStockListInstance)

                return Response("Success", status=status.HTTP_201_CREATED)
        
        except Exception as e:
            return Response({"detail" : f'Error {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class UpdateProduct(GestionnaireEditorMixin, generics.RetrieveUpdateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerialiser
    lookup_field = 'pk'

    def patch(self, request, *args, **kwargs):
        datas = request.data
        user = request.user

        with transaction.atomic():
            
            qte_gros = int(datas['qte_gros'])
            product = Product.objects.get(pk = datas['pk'])
            prix_gros = datas['prix_gros'] if datas['prix_gros'] else product.prix_gros
            prix_gros_achat = datas['prix_gros_achat'] if datas['prix_gros_achat'] else product.prix_gros_achat
            #Historique De mise a jour de produit
            AjoutStock.objects.create(
                qte_gros_transaction=qte_gros,
                # qte_detail_transaction=qte_detail,
                type_transaction="Maj",
                prix_gros = prix_gros,
                prix_gros_achat = prix_gros_achat,
                # prix_detail = prix_detail,
                prix_total = (int(prix_gros) * int( qte_gros)),
                product=product,
                gestionnaire=user   
            )

            if int(qte_gros)<0:
                return Response({"message" : "Les valeurs ne peuvent pas être negatif"}, status=status.HTTP_400_BAD_REQUEST)
            if  int(qte_gros)>0:
                # qte_gros += product.qte_gros
                # qte_detail += product.qte_detail
                detailInstance = product.detail
                print("Designation", detailInstance.designation)
                print("GROS", qte_gros)
                request.data['qte_gros'] = qte_gros
            else :
                request.data.pop("qte_gros")
                print(request.data)
            
        return super().patch(request, *args, **kwargs)
    
class DeleteProduct(generics.DestroyAPIView, generics.ListAPIView, GestionnaireEditorMixin):
    queryset = Product.objects.all()
    serializer_class = ProductSerialiser

class SellProduct(VendeurEditorMixin, generics.ListCreateAPIView):
    queryset = VenteProduct.objects.all()
    serializer_class = VenteProductSerializer

    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        try:
            user = self.request.user
            prix_gros = 0
            produit = Product.objects.filter(id=serializer.validated_data.get('product_id')).first()
            qte_gros = serializer.validated_data.get('qte_gros_transaction')
            if qte_gros > 0 :
                produit.qte_gros -= qte_gros
                prix_gros = qte_gros * produit.qte_gros
            produit.save()
            facture = Facture.objects.create(
                prix_total = prix_gros ,
                prix_restant = 0,
                owner = user
            )

            serializer.save(facture = facture)
            instanceP = serializer.instance
        #Capture l'erreur de validation
        except ValidationError as e:
            raise e
        except Exception as e:
            raise BaseException()

class SellBulkProduct(VendeurEditorMixin, generics.ListCreateAPIView):
    queryset = VenteProduct.objects.all()
    serializer_class = VenteProductSerializer
    
    def post(self, request):
        datas = request.data
        client = ""
        user = request.user
        prixRestant = 0
        datasCopy = datas.copy()
        
        for item in datasCopy:
            for key, value in item.items():
                if key == "client":
                    client = value
                    datas.remove(item)
                if key == "prix_restant":
                    prixRestant = value
                    datas.remove(item)
                    
        venteList = datas
        venteInstancList = []
        
        try:
            with transaction.atomic():
                facture = Facture(
                    prix_total=0,
                    prix_restant=0,
                    owner=user
                )
                # prix_unit = 0
                prix_gros = 0
                # prix_detail = 0
                
                for vente in venteList:
                    print("Vente", vente)
                    product_id = vente['product_id']
                    new_prix_vente = vente['new_prix_vente']
                    try:
                        produit = Product.objects.get(id=product_id)
                    except Product.DoesNotExist:
                        return Response({"message": "Produit introuvable"}, status=status.HTTP_404_NOT_FOUND)

                    qteGrosVente = vente['qte_gros_transaction']
                    
                    if qteGrosVente < 0 :
                        return Response({"message": "Erreur de quantité de vente"}, status=status.HTTP_400_BAD_REQUEST)
                    
                    qteGrosStock = produit.qte_gros
                    #CONVERSION
                    #Condition
                    if qteGrosStock >= qteGrosVente:
                        qteGrosStock -= qteGrosVente
                    else:
                        return Response({"message": 'La quantité est invalide ou dépasse le stock'}, status=status.HTTP_400_BAD_REQUEST)
                    
                    # produit.qte_unit = qteUnitStock
                    produit.qte_gros = qteGrosStock
                    # produit.qte_detail = qteDetailStock
                    
                    venteInstance = VenteProduct(
                        product=produit,
                        # qte_unit_transaction=qteUnitVente,
                        prix_vente = new_prix_vente if new_prix_vente else produit.prix_gros,
                        qte_gros_transaction=qteGrosVente,
                        # qte_detail_transaction=qteDetailVente,
                        type_transaction="Vente",
                        prix_total=(int(qteGrosVente * new_prix_vente) if new_prix_vente
                                    else
                                        int(qteGrosVente * produit.prix_gros)),
                        facture=facture,
                    )
                    
                    produit.save()
                    prix_gros += int(qteGrosVente * new_prix_vente) if new_prix_vente else  int(qteGrosVente * produit.prix_gros)
                    
                    venteInstancList.append(venteInstance)
                
                facture.prix_restant = prixRestant
                facture.prix_total =  prix_gros 
                facture.client = client
                facture.save()
                
                if len(venteInstancList) > 0:
                    VenteProduct.objects.bulk_create(venteInstancList)
                    factureData = Facture.objects.filter(pk=facture.pk).first()
                    factureDatas = FactureSerialiser(factureData).data
                    return Response(factureDatas, status=status.HTTP_201_CREATED)
                else:
                    return Response({'message': "Erreur de création"}, status=status.HTTP_400_BAD_REQUEST)
        except AttributeError as e:
            return Response({"message": f"Erreur d'attribut{e}"}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"message": f"Erreur: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreateFilAttenteProduct(VendeurEditorMixin, generics.ListCreateAPIView):
    queryset = VenteProduct.objects.all()
    serializer_class = VenteProductSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        filtre = {"type_transaction" : "attente"}
        return qs.filter(**filtre)

    def post(self, request):
        datas = request.data
        client = ""
        user = request.user
        prixRestant = 0
        datasCopy = datas.copy()
        
        for item in datasCopy:
            for key, value in item.items():
                if key == "client":
                    client = value
                    datas.remove(item)
                if key == "prix_restant":
                    prixRestant = value
                    datas.remove(item)
                    
        venteList = datas
        venteInstancList = []
        
        try:
            with transaction.atomic():
                filAttente = FilAttenteProduct(
                    prix_total=0,
                    prix_restant=0,
                    owner=user
                )
                filAttente.save()
                prix_gros = 0
                
                for vente in venteList:
                    print("Vente", vente)
                    product_id = vente['product_id']
                    new_prix_vente = vente.get('new_prix_vente', None)
                    try:
                        produit = Product.objects.get(id=product_id)
                    except Product.DoesNotExist:
                        return Response({"message": "Produit introuvable"}, status=status.HTTP_404_NOT_FOUND)
                    
                    qteGrosVente = vente['qte_gros_transaction']
                    
                    if qteGrosVente < 0 :
                        return Response({"message": "Erreur de quantité de vente"}, status=status.HTTP_400_BAD_REQUEST)
                    
                    qteGrosStock = produit.qte_gros
                    
                    #Condition
                    if qteGrosStock >= qteGrosVente:
                        if qteGrosStock < qteGrosVente:
                            return Response({"message": "Stock insuffisant"}, status=status.HTTP_400_BAD_REQUEST)
                        qteGrosStock -= qteGrosVente
                    else:
                        return Response({"message": 'La quantité est invalide ou dépasse le stock'}, status=status.HTTP_400_BAD_REQUEST)
                    
                    produit.qte_gros = qteGrosStock
                    venteInstance = VenteProduct(
                        product=produit,
                        qte_gros_transaction=qteGrosVente,
                        prix_vente = new_prix_vente if new_prix_vente else produit.prix_gros,
                        type_transaction="Attente",
                        prix_total=(int(qteGrosVente * new_prix_vente) if new_prix_vente
                                    else
                                        int(qteGrosVente * produit.prix_gros)),
                        fil_attente=filAttente,
                    )
                    
                    produit.save()
                    prix_gros += int(qteGrosVente * new_prix_vente) if new_prix_vente else  int(qteGrosVente * produit.prix_gros)
                    
                    venteInstancList.append(venteInstance)
                
                filAttente.prix_restant = prixRestant
                filAttente.prix_total =  prix_gros
                filAttente.client = client
                filAttente.save()

                # print("VenteList", venteInstancList)
                
                if len(venteInstancList) > 0:
                    print("ATO", filAttente.id)
                    VenteProduct.objects.bulk_create(venteInstancList)
                    # filDatas = FilAttenteProduct.objects.filter(id__iexact = filAttente.id).first()
                    filAttentesSerialiser = FilAttenteSerialiser(filAttente).data
                    
                    return Response(filAttentesSerialiser, status=status.HTTP_201_CREATED)
                else:
                    return Response({'message': "Erreur de création"}, status=status.HTTP_400_BAD_REQUEST)
                
        except AttributeError as e:
            return Response({"message": f"Erreur d'attribut{e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({"message": f"Erreur: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ValidateFilAttente(VendeurEditorMixin, generics.ListCreateAPIView):
    queryset = VenteProduct.objects.all()
    serializer_class = VenteProductSerializer

    def create(self, request, *args, **kwargs):
        try:
            filId = kwargs['pk']
            venteList = FilAttenteProduct.finaliser(self, id=filId)
            print("Les ventes", venteList)
            return Response(data=VenteProductSerializer(venteList, many = True).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"message" : f"Erreur {e}"})

class CancelFilAttente(VendeurEditorMixin, generics.RetrieveDestroyAPIView):
    queryset = FilAttenteProduct.objects.all()
    serializer_class = FilAttenteSerialiser
    lookup_field = 'pk'
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        print("Object to delete", instance)
        listVente = instance.venteproduct_related.all()
        with transaction.atomic():
            try:
                productList = []
                for vente in listVente:
                    product = Product.objects.get(id = vente.product.id)
                    qte_gros_cancel = vente.qte_gros_transaction
                    product.qte_gros += qte_gros_cancel
                    productList.append(product)
                    product.save()
                    vente.delete()
                
                self.perform_destroy(instance)
                return Response(status=status.HTTP_200_OK, data=ProductSerialiser(productList, many = True).data)
            except Product.DoesNotExist:
                return Response({"message": "Produit introuvable"}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                return Response({"message": f"Erreur Serveur {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class UpdateFilAttente(VendeurEditorMixin, generics.UpdateAPIView):
    queryset = VenteProduct.objects.all()
    serializer_class = VenteProductSerializer

    def update(self, request, *args, **kwargs):
        filId = kwargs['pk']
        
        try:
            client = None
            prixRestant = None
            datas = request.data
            datasCopy = datas.copy()
            filAttente = FilAttenteProduct.objects.get(id=filId)
            for item in datasCopy:
                for key, value in item.items():
                    if key == "client":
                        client = value
                        datas.remove(item)
                    if key == "prix_restant":
                        prixRestant = value
                        datas.remove(item)
                     
            venteInstanceList = []
            newVenteInstanceList = []
            newPrixGrosVenteTotal = 0
            with transaction.atomic():
                for vente in datas:
                    productId = vente.get('product_id', None)
                    new_prix_vente = vente.get('new_prix_vente', None)
                    if productId :
                        try:
                            produit = Product.objects.get(id=productId)
                        except Product.DoesNotExist:
                            return Response({"message": "Produit introuvable"}, status=status.HTTP_404_NOT_FOUND)
                        
                        qteGrosVente = vente['qte_gros_transaction']
                        
                        if qteGrosVente < 0 :
                            return Response({"message": "Erreur de quantité de vente"}, status=status.HTTP_400_BAD_REQUEST)
                        
                        qteGrosStock = produit.qte_gros
                        #Condition
                        if qteGrosStock >= qteGrosVente:
                            if qteGrosStock < qteGrosVente:
                                return Response({"message": "Stock insuffisant"}, status=status.HTTP_400_BAD_REQUEST)
                            qteGrosStock -= qteGrosVente
                        else:
                            return Response({"message": 'La quantité est invalide ou dépasse le stock'}, status=status.HTTP_400_BAD_REQUEST)
                        
                        produit.qte_gros = qteGrosStock

                        newVenteInstance = VenteProduct(
                            product=produit,
                            prix_vente = new_prix_vente if new_prix_vente else produit.prix_gros,
                            type_transaction="Attente",
                            qte_gros_transaction = qteGrosVente,
                            prix_total=(int(qteGrosVente * new_prix_vente) if new_prix_vente
                                    else
                                        int(qteGrosVente * produit.prix_gros)),
                            fil_attente=filAttente,
                        )
                        
                        produit.save()
                        newPrixGrosVenteTotal += int(qteGrosVente * new_prix_vente) if new_prix_vente else  int(qteGrosVente * produit.prix_gros)
                        newVenteInstanceList.append(newVenteInstance)

                    else :
                        venteId = vente["id"]
                        venteInstance = VenteProduct.objects.get(id = venteId)
                        product = venteInstance.product
                        print("Produit", product)
                        newQteGros = int(vente["qte_gros_transaction"])
                        product.qte_gros +=  venteInstance.qte_gros_transaction
                        venteInstance.qte_gros_transaction = newQteGros
                        product.qte_gros -= newQteGros
                        product.save()
                        venteInstance.prix_vente = int(new_prix_vente) if new_prix_vente else product.prix_gros
                        venteInstance.prix_total = (int(newQteGros * new_prix_vente) if new_prix_vente
                                                    else
                                                    int(newQteGros * product.prix_gros))
                        venteInstanceList.append(venteInstance)
                #Zero s'il n'y avait pas d'ajout de produit
                filAttente.prix_total =  newPrixGrosVenteTotal
                if len(venteInstanceList) > 0:
                    VenteProduct.objects.bulk_update(venteInstanceList, fields=["qte_gros_transaction", "date", "prix_total", "prix_vente"])
                for vente in venteInstanceList:
                    filAttente.prix_total += vente.prix_total
                if prixRestant:
                    filAttente.prix_restant = prixRestant
                if client:
                    filAttente.prix_restant = client
                filAttente.save()
                if len(newVenteInstanceList) > 0:
                    VenteProduct.objects.bulk_create(newVenteInstanceList)
            return Response(FilAttenteSerialiser(filAttente).data, status=status.HTTP_205_RESET_CONTENT) 
        except FilAttenteProduct.DoesNotExist:
            return Response({"message":"Fil d'attente introuvale"})
        except AttributeError as e:
            return Response({"message": f"Erreur d'attribut{e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({"message" : f"Error ${e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ListFilAttente(generics.ListAPIView, userFactureQs):
    queryset = FilAttenteProduct.objects.all()
    serializer_class = FilAttenteSerialiser

class ListVente(generics.ListAPIView):
    queryset = VenteProduct.objects.all()
    serializer_class = VenteProductSerializer

class DeleteVente(VendeurEditorMixin, generics.DestroyAPIView):
    queryset = VenteProduct.objects.all()
    serializer_class = VenteProductSerializer

    def destroy(self, request, *args, **kwargs):
        instance : VenteProduct = self.get_object()
        try:
            with transaction.atomic():
                product : Product = instance.product
                product.qte_gros += instance.qte_gros_transaction
                product.save()
                facture : Facture = instance.facture
                filAttente = instance.fil_attente
                print("Insatance", instance.id)
                self.perform_destroy(instance)

                if facture:
                    venteList = facture.venteproduct_related.all()
                    facture.prix_total = 0
                    for vente  in venteList:
                        facture.prix_total += vente.qte_gros_transaction * vente.prix_vente
                    facture.save()
                elif filAttente:
                    venteList = filAttente.venteproduct_related.all()
                    filAttente.prix_total = 0
                    for vente  in venteList:
                        filAttente.prix_total += vente.qte_gros_transaction * vente.prix_vente
                    filAttente.save()

            return Response(status=status.HTTP_204_NO_CONTENT)
        except AttributeError as e:
            return Response({"message": f"Erreur d'attribut{e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({"message" : f"Error ${e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class ListTransactions(GestionnaireEditorMixin, generics.ListAPIView):
    queryset = AjoutStock.objects.all()
    serializer_class = AjoutStockSerialiser

class RetrieveTransactions(GestionnaireEditorMixin, generics.RetrieveAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerialiser
    lookup_field = 'pk'

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        ajout = instance.ajoutstock_related.all()
        serializer = self.get_serializer(instance)
        ajoutsersialiser = AjoutStockSerialiser(ajout, many = True).data
        return Response(ajoutsersialiser)

##Mbola ts vita
class CancelFacture(VendeurEditorMixin, generics.RetrieveDestroyAPIView):
    queryset = Facture.objects.all()
    serializer_class = FactureSerialiser
    lookup_field = 'pk'
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        print("Object to delete", instance)
        listVente = instance.venteproduct_related.all()
        with transaction.atomic():
            try:
                for vente in listVente:
                    product = Product.objects.get(id = vente.product.id)

                    qte_gros_cancel = vente.qte_gros_transaction
                    product.qte_gros += qte_gros_cancel
                    product.save()
                    
                self.perform_destroy(instance)
                return Response(status=status.HTTP_200_OK, data=ProductSerialiser(product).data)
            except Product.DoesNotExist:
                return Response({"message": "Produit introuvable"}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                return Response({"message": f"Erreur Serveur {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
class ListFacture(generics.ListAPIView, userFactureQs):
    queryset = Facture.objects.all()
    serializer_class = FactureSerialiser
    # permission_classes = [IsAuthenticated, ]
    
class DeleteFacture(generics.DestroyAPIView):
    queryset = Facture.objects.all()
    serializer_class = FactureSerialiser

class UpdateFacture(generics.RetrieveUpdateAPIView):
    queryset = Facture.objects.all()
    serializer_class = FactureSerialiser
    lookup_field = 'pk'
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        old_prix_restant = instance.prix_restant

        with transaction.atomic():  # Tout est dans une transaction
            # Valider les données avant de les appliquer
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)

            # Appliquer la mise à jour
            self.perform_update(serializer)

            # Recharger les données mises à jour
            instance.refresh_from_db()
            new_prix_restant = instance.prix_restant
            print("Facture", new_prix_restant)
            new_prix_restant = instance.prix_restant
            montant_regle = old_prix_restant - new_prix_restant
            print("montant regele", montant_regle)
            if montant_regle > 0:
                # Création du règlement (rollback automatique si erreur ici)
                Reglement.objects.create(
                    content_type=ContentType.objects.get_for_model(instance),
                    object_id=instance.id,
                    montant=montant_regle
                )

        queryset = self.filter_queryset(self.get_queryset())
        if queryset._prefetch_related_lookups:
            instance._prefetched_objects_cache = {}
            prefetch_related_objects([instance], *queryset._prefetch_related_lookups)

        return Response(serializer.data)
       
# /*** TROSA  ****/
class CreateTrosa(generics.CreateAPIView):
    queryset = Trosa.objects.all()
    serializer_class = TrosaSerialiser

class ListTrosa(generics.ListAPIView):
    queryset = Trosa.objects.all()
    serializer_class = TrosaSerialiser

class DeleteTrosa(generics.RetrieveDestroyAPIView):
    queryset = Trosa.objects.all()
    serializer_class = TrosaSerialiser

class UpdateTrosa(generics.RetrieveUpdateAPIView):
    queryset = Trosa.objects.all()
    serializer_class = TrosaSerialiser

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        old_prix_restant = instance.montant_restant

        with transaction.atomic():  # Tout est dans une transaction
            # Valider les données avant de les appliquer
            serializer = self.get_serializer(instance, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)

            # Appliquer la mise à jour
            self.perform_update(serializer)

            # Recharger les données mises à jour
            instance.refresh_from_db()
            new_prix_restant = instance.montant_restant

            new_prix_restant = instance.montant_restant
            montant_regle = old_prix_restant - new_prix_restant

            if montant_regle > 0:
                # Création du règlement (rollback automatique si erreur ici)
                Reglement.objects.create(
                    content_type=ContentType.objects.get_for_model(instance),
                    object_id=instance.id,
                    montant=montant_regle
                )

        queryset = self.filter_queryset(self.get_queryset())
        if queryset._prefetch_related_lookups:
            instance._prefetched_objects_cache = {}
            prefetch_related_objects([instance], *queryset._prefetch_related_lookups)

        return Response(serializer.data)
 
class ListFournisseur(generics.ListAPIView):
    queryset = Fournisseur.objects.all()
    serializer_class = FournisseurSerialiser

class UpdateFournisserur(generics.UpdateAPIView):
    queryset = Fournisseur.objects.all()
    serializer_class = FournisseurSerialiser
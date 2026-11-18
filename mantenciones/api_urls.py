from django.urls import path

from mantenciones import api

app_name = "api"

urlpatterns = [
    path("sesion/", api.sesion, name="sesion"),
    path("paquete/", api.paquete, name="paquete"),
    path("cloudinary/firma/", api.firma_cloudinary, name="firma"),
    path("mantenciones/sincronizar/", api.sincronizar, name="sincronizar"),
]

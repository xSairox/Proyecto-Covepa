from django.urls import path

from mantenciones import views

app_name = "mantenciones"

urlpatterns = [
    path("inicio/", views.inicio_tecnico, name="inicio"),
    path("registrar/", views.registrar, name="registrar"),
    path("historial/", views.HistorialLista.as_view(), name="historial"),
    path("registro/<uuid:pk>/", views.registro_detalle, name="detalle"),
    path("plantillas/", views.plantillas_lista, name="plantillas"),
    path("plantillas/nueva/", views.plantilla_form, name="plantilla_nueva"),
    path("plantillas/<int:pk>/", views.plantilla_form, name="plantilla_editar"),
    path("planes/", views.planes_lista, name="planes"),
    path("planes/nuevo/", views.plan_form, name="plan_nuevo"),
    path("planes/<int:pk>/", views.plan_form, name="plan_editar"),
]

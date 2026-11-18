from django.urls import path

from inventario import views

app_name = "inventario"

urlpatterns = [
    path("", views.EquiposLista.as_view(), name="lista"),
    path("nuevo/", views.equipo_nuevo, name="nuevo"),
    path("<int:pk>/", views.equipo_detalle, name="detalle"),
    path("<int:pk>/editar/", views.equipo_editar, name="editar"),
    path("<int:pk>/baja/", views.equipo_baja, name="baja"),
    path("<int:pk>/versiones/nueva/", views.version_nueva, name="version_nueva"),
]

from django.urls import path

from notificaciones import views

app_name = "notificaciones"

urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:pk>/leer/", views.marcar_leida, name="leer"),
    path("leer-todas/", views.marcar_todas, name="leer_todas"),
]

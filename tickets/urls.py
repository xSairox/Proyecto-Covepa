from django.urls import path

from tickets import views

app_name = "tickets"

urlpatterns = [
    path("", views.TicketsLista.as_view(), name="lista"),
    path("nuevo/", views.ticket_nuevo, name="nuevo"),
    path("<int:pk>/", views.ticket_detalle, name="detalle"),
    path("<int:pk>/<str:accion>/", views.ticket_accion, name="accion"),
]

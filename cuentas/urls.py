from django.urls import path

from cuentas import views

app_name = "cuentas"

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.cerrar_sesion, name="logout"),
    path("2fa/", views.dos_pasos, name="dos_pasos"),
    path("2fa/configurar/", views.dos_pasos_configurar, name="dos_pasos_configurar"),
    path("activar/<str:token>/", views.activar, name="activar"),
    path("recuperar/", views.recuperar_solicitar, name="recuperar"),
    path("recuperar/<str:token>/", views.recuperar_confirmar, name="recuperar_confirmar"),
    path("perfil/", views.perfil, name="perfil"),
    path("perfil/clave/", views.CambiarClave.as_view(), name="cambiar_clave"),
    path("usuarios/", views.UsuariosLista.as_view(), name="usuarios"),
    path("usuarios/nuevo/", views.usuario_nuevo, name="usuario_nuevo"),
    path("usuarios/<int:pk>/", views.usuario_editar, name="usuario_editar"),
    path("usuarios/<int:pk>/estado/", views.usuario_estado, name="usuario_estado"),
    path("usuarios/<int:pk>/invitar/", views.usuario_reinvitar, name="usuario_reinvitar"),
]

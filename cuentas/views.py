import segno
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import FormView, ListView

from auditoria import services as auditoria
from core.permisos import JEFATURA, PerfilRequeridoMixin, perfil_requerido
from cuentas import services
from cuentas.forms import (
    FormularioCambiarClave,
    FormularioCodigo,
    FormularioLogin,
    FormularioNuevaClave,
    FormularioRecuperar,
    FormularioUsuario,
)
from cuentas.models import Perfil, TokenAcceso, Usuario


def _destino_seguro(request, defecto="inicio"):
    destino = request.POST.get("next") or request.GET.get("next") or ""
    if destino and url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return destino
    return reverse(defecto)


# --------------------------------------------------------------------------- inicio y cierre de sesión


class LoginView(FormView):
    template_name = "registration/login.html"
    form_class = FormularioLogin

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("inicio")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["next"] = self.request.GET.get("next", "")
        return ctx

    def form_valid(self, form):
        usuario = form.usuario
        services.reiniciar_intentos(usuario)
        login(self.request, usuario, backend="cuentas.backends.CorreoBackend")
        self.request.session["otp_verificado"] = False
        auditoria.registrar(usuario, auditoria.LOGIN_OK, "usuario", usuario.pk, request=self.request)
        return redirect(_destino_seguro(self.request))


@require_POST
def cerrar_sesion(request):
    if request.user.is_authenticated:
        auditoria.registrar(request.user, auditoria.LOGOUT, "usuario", request.user.pk, request=request)
    logout(request)
    return redirect("cuentas:login")


# --------------------------------------------------------------------------- segundo factor


@login_required
def dos_pasos(request):
    usuario = request.user
    if not usuario.perfil.requiere_dos_pasos or request.session.get("otp_verificado"):
        return redirect("inicio")
    if not usuario.dos_pasos_activo:
        return redirect("cuentas:dos_pasos_configurar")
    form = FormularioCodigo(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if services.verificar_codigo_totp(usuario, form.cleaned_data["codigo"]):
            request.session["otp_verificado"] = True
            services.reiniciar_intentos(usuario)
            return redirect(_destino_seguro(request))
        bloqueada = services.registrar_fallo(usuario, usuario.correo, request, accion=auditoria.DOS_PASOS_FALLIDO)
        if bloqueada:
            logout(request)
            messages.error(request, "Demasiados códigos incorrectos: la cuenta quedó bloqueada temporalmente.")
            return redirect("cuentas:login")
        form.add_error("codigo", "Código incorrecto.")
    return render(request, "cuentas/dos_pasos.html", {"form": form})


@login_required
def dos_pasos_configurar(request):
    usuario = request.user
    if not usuario.perfil.requiere_dos_pasos:
        return redirect("inicio")
    if usuario.dos_pasos_activo:  # no se vuelve a mostrar el secreto
        return redirect("cuentas:dos_pasos")
    secreto = services.asegurar_secreto_totp(usuario)
    form = FormularioCodigo(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if services.verificar_codigo_totp(usuario, form.cleaned_data["codigo"]):
            usuario.dos_pasos_activo = True
            usuario.save(update_fields=["dos_pasos_activo"])
            request.session["otp_verificado"] = True
            auditoria.registrar(usuario, auditoria.DOS_PASOS_ACTIVADO, "usuario", usuario.pk, request=request)
            messages.success(request, "Verificación en dos pasos activada.")
            return redirect("inicio")
        form.add_error("codigo", "Código incorrecto. Revisa la hora de tu teléfono e inténtalo de nuevo.")
    qr = segno.make(services.uri_totp(usuario), error="m").svg_data_uri(scale=5, border=2)
    return render(request, "cuentas/dos_pasos_configurar.html", {"form": form, "qr": qr, "secreto": secreto})


# --------------------------------------------------------------------------- contraseñas por enlace


def _definir_clave(request, token, tipo, titulo, ayuda):
    objeto = TokenAcceso.buscar_vigente(token, tipo)
    if objeto is None:
        return render(request, "cuentas/enlace_invalido.html", status=410)
    form = FormularioNuevaClave(objeto.usuario, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        objeto.consumir()
        usuario = objeto.usuario
        services.reiniciar_intentos(usuario)
        auditoria.registrar(usuario, auditoria.CONTRASENA_DEFINIDA, "usuario", usuario.pk, {"origen": tipo}, request)
        messages.success(request, "Contraseña definida. Ya puedes iniciar sesión.")
        return redirect("cuentas:login")
    return render(request, "cuentas/definir_clave.html", {"form": form, "titulo": titulo, "ayuda": ayuda})


def activar(request, token):
    return _definir_clave(
        request, token, TokenAcceso.INVITACION, "Activa tu cuenta", "Define la contraseña con la que ingresarás al sistema."
    )


def recuperar_solicitar(request):
    form = FormularioRecuperar(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = Usuario.objects.filter(correo=form.cleaned_data["correo"].strip().lower(), is_active=True).first()
        if usuario:
            services.enviar_enlace(request, usuario, TokenAcceso.RECUPERACION)
        # Misma respuesta exista o no la cuenta: no revela qué correos están registrados.
        messages.info(request, "Si el correo está registrado, te enviamos un enlace para definir una contraseña nueva.")
        return redirect("cuentas:login")
    return render(request, "cuentas/recuperar.html", {"form": form})


def recuperar_confirmar(request, token):
    return _definir_clave(
        request, token, TokenAcceso.RECUPERACION, "Nueva contraseña", "El enlace es de un solo uso y vence en 1 hora."
    )


# --------------------------------------------------------------------------- mi perfil


@login_required
def perfil(request):
    return render(request, "cuentas/perfil.html", {"permisos": request.user.perfil.permisos})


class CambiarClave(PasswordChangeView):
    form_class = FormularioCambiarClave
    template_name = "cuentas/cambiar_clave.html"
    success_url = reverse_lazy("cuentas:perfil")

    def form_valid(self, form):
        messages.success(self.request, "Contraseña actualizada.")
        return super().form_valid(form)


# --------------------------------------------------------------------------- gestión de usuarios (HU-01)


class UsuariosLista(PerfilRequeridoMixin, ListView):
    perfiles = (JEFATURA,)
    template_name = "cuentas/usuarios_lista.html"
    context_object_name = "usuarios"
    paginate_by = 30

    def get_queryset(self):
        qs = Usuario.objects.select_related("perfil", "sucursal")
        g = self.request.GET
        if g.get("q"):
            q = g["q"].strip()
            qs = qs.filter(Q(nombre__icontains=q) | Q(apellido__icontains=q) | Q(correo__icontains=q))
        if g.get("perfil"):
            qs = qs.filter(perfil__codigo=g["perfil"])
        if g.get("estado") in {"activo", "inactivo"}:
            qs = qs.filter(is_active=(g["estado"] == "activo"))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["perfiles"] = Perfil.objects.all()
        ctx["filtros"] = self.request.GET
        return ctx


@perfil_requerido(JEFATURA)
def usuario_nuevo(request):
    form = FormularioUsuario(request.POST or None)
    if request.method == "POST" and form.is_valid():
        usuario = form.save(commit=False)
        usuario.set_unusable_password()  # la persona define su contraseña con el enlace de invitación
        usuario.save()
        enlace = services.enviar_enlace(request, usuario, TokenAcceso.INVITACION)
        auditoria.registrar(
            request.user, auditoria.USUARIO_CREADO, "usuario", usuario.pk, {"perfil": usuario.perfil.codigo}, request
        )
        messages.success(request, f"Usuario creado. Enlace de activación (válido {settings.POLITICAS['INVITACION_HORAS']} h): {enlace}")
        return redirect("cuentas:usuarios")
    return render(request, "cuentas/usuario_form.html", {"form": form, "titulo": "Nuevo usuario"})


@perfil_requerido(JEFATURA)
def usuario_editar(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    form = FormularioUsuario(request.POST or None, instance=usuario)
    if request.method == "POST" and form.is_valid():
        form.save()
        auditoria.registrar(request.user, auditoria.USUARIO_EDITADO, "usuario", usuario.pk, {"campos": form.changed_data}, request)
        messages.success(request, "Usuario actualizado.")
        return redirect("cuentas:usuarios")
    return render(request, "cuentas/usuario_form.html", {"form": form, "titulo": f"Editar a {usuario}", "usuario_editado": usuario})


@require_POST
@perfil_requerido(JEFATURA)
def usuario_estado(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    if usuario.pk == request.user.pk:
        messages.error(request, "No puedes desactivar tu propia cuenta.")
        return redirect("cuentas:usuarios")
    if usuario.is_active:
        usuario.desactivar()
        auditoria.registrar(request.user, auditoria.USUARIO_DESACTIVADO, "usuario", usuario.pk, request=request)
        messages.success(request, f"{usuario} fue desactivado y se cerraron sus sesiones.")
    else:
        usuario.is_active = True
        usuario.save(update_fields=["is_active"])
        auditoria.registrar(request.user, auditoria.USUARIO_EDITADO, "usuario", usuario.pk, {"reactivado": True}, request)
        messages.success(request, f"{usuario} fue reactivado.")
    return redirect("cuentas:usuarios")


@require_POST
@perfil_requerido(JEFATURA)
def usuario_reinvitar(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk, is_active=True)
    enlace = services.enviar_enlace(request, usuario, TokenAcceso.INVITACION)
    messages.success(request, f"Nuevo enlace de activación para {usuario}: {enlace}")
    return redirect("cuentas:usuarios")

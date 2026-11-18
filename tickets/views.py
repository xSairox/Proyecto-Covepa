from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from auditoria import services as auditoria
from core.permisos import (
    AUDITOR,
    JEFATURA,
    TECNICO_EXTERNO,
    TECNICO_INTERNO,
    TRABAJADOR,
    PerfilRequeridoMixin,
    perfil_requerido,
)
from tickets import estados, services
from tickets.forms import FormularioAprobar, FormularioMotivo, FormularioRealizar, FormularioTicket
from tickets.models import Ticket

TODOS = (JEFATURA, TECNICO_INTERNO, TECNICO_EXTERNO, TRABAJADOR, AUDITOR)


def _ticket_o_403(request, pk) -> Ticket:
    ticket = get_object_or_404(Ticket.objects.select_related("equipo", "solicitante", "tecnico"), pk=pk)
    if not services.tickets_visibles(request.user).filter(pk=pk).exists():
        auditoria.registrar(request.user, auditoria.ACCESO_DENEGADO, "ticket", pk, {"ruta": request.path}, request)
        raise PermissionDenied("No tienes acceso a este ticket.")
    return ticket


class TicketsLista(PerfilRequeridoMixin, ListView):
    perfiles = TODOS
    template_name = "tickets/lista.html"
    context_object_name = "tickets"
    paginate_by = 25

    def get_queryset(self):
        qs = services.tickets_visibles(self.request.user)
        g = self.request.GET
        if g.get("estado") in estados.ESTADOS:
            qs = qs.filter(estado=g["estado"])
        elif g.get("estado") == "abiertos":
            qs = qs.exclude(estado__in=estados.ESTADOS_FINALES)
        if g.get("q"):
            q = g["q"].strip()
            qs = qs.filter(Q(descripcion__icontains=q) | Q(equipo__codigo__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["estados"] = estados.ESTADOS
        ctx["filtros"] = self.request.GET
        ctx["puede_crear"] = self.request.user.tiene_permiso("tickets.crear")
        return ctx


@perfil_requerido(JEFATURA, TECNICO_INTERNO, TRABAJADOR)
def ticket_nuevo(request):
    form = FormularioTicket(request.POST or None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            ticket = services.crear_ticket(
                request.user,
                form.cleaned_data.get("tipo", Ticket.FALLA),
                form.cleaned_data["descripcion"],
                form.cleaned_data.get("equipo"),
                request,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"Ticket {ticket.numero} creado. La jefatura recibió el aviso.")
            return redirect("tickets:detalle", pk=ticket.pk)
    return render(request, "tickets/form.html", {"form": form})


@perfil_requerido(*TODOS)
def ticket_detalle(request, pk):
    ticket = _ticket_o_403(request, pk)
    u = request.user
    es_asignado = ticket.tecnico_id == u.pk
    contexto = {
        "ticket": ticket,
        "historial": ticket.historial.select_related("usuario"),
        "materiales": ticket.materiales.all(),
        "documentos": ticket.documentos.all(),
        "puede_aprobar": u.tiene_permiso("tickets.aprobar") and ticket.estado == estados.PENDIENTE,
        "puede_iniciar": u.tiene_permiso("tickets.ejecutar") and es_asignado and ticket.estado == estados.APROBADO,
        "puede_realizar": u.tiene_permiso("tickets.ejecutar") and es_asignado and ticket.estado == estados.EN_EJECUCION,
        "puede_cerrar": u.tiene_permiso("tickets.cerrar") and ticket.estado == estados.REALIZADO,
    }
    if contexto["puede_aprobar"]:
        contexto["form_aprobar"] = FormularioAprobar(ticket=ticket)
        contexto["form_motivo"] = FormularioMotivo()
    if contexto["puede_cerrar"]:
        contexto["form_motivo"] = FormularioMotivo()
    if contexto["puede_realizar"]:
        contexto["form_realizar"] = FormularioRealizar()
    return render(request, "tickets/detalle.html", contexto)


@require_POST
@perfil_requerido(*TODOS)
def ticket_accion(request, pk, accion):
    ticket = _ticket_o_403(request, pk)
    u = request.user
    try:
        if accion == "aprobar":
            form = FormularioAprobar(request.POST, ticket=ticket)
            if not form.is_valid():
                raise ValidationError("Elige un técnico de la lista.")
            services.aprobar(ticket, u, form.cleaned_data["tecnico"], request)
            messages.success(request, f"Ticket aprobado y asignado a {ticket.tecnico}.")
        elif accion == "rechazar":
            form = FormularioMotivo(request.POST)
            if not form.is_valid():
                raise ValidationError("Indica el motivo del rechazo.")
            services.rechazar(ticket, u, form.cleaned_data["motivo"], request)
            messages.success(request, "Ticket rechazado.")
        elif accion == "iniciar":
            services.iniciar(ticket, u, request)
            messages.success(request, "Trabajo iniciado.")
        elif accion == "realizar":
            form = FormularioRealizar(request.POST)
            if not form.is_valid():
                raise ValidationError([m for lista in form.errors.values() for m in lista])
            services.realizar(
                ticket, u, form.cleaned_data["materiales_json"], form.cleaned_data["documentos_json"], form.cleaned_data["observacion"], request
            )
            messages.success(request, "Trabajo registrado. La jefatura fue avisada para revisarlo.")
        elif accion == "cerrar":
            services.cerrar(ticket, u, request)
            messages.success(request, "Ticket cerrado.")
        elif accion == "devolver":
            form = FormularioMotivo(request.POST)
            if not form.is_valid():
                raise ValidationError("Indica qué debe corregir el técnico.")
            services.devolver(ticket, u, form.cleaned_data["motivo"], request)
            messages.success(request, "Ticket devuelto al técnico con tus observaciones.")
        else:
            raise ValidationError("Acción desconocida.")
    except ValidationError as exc:
        for mensaje in exc.messages:
            messages.error(request, mensaje)
    return redirect("tickets:detalle", pk=pk)

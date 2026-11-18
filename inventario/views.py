from django.contrib import messages
from django.db.models import Q
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST
from django.views.generic import ListView

from auditoria import services as auditoria
from core.permisos import JEFATURA, TECNICO_EXTERNO, TECNICO_INTERNO, PerfilRequeridoMixin, perfil_requerido
from inventario.forms import FormularioEquipo, FormularioVersion
from inventario.models import Categoria, Equipo
from inventario.selectors import equipo_o_403, equipos_visibles


class EquiposLista(PerfilRequeridoMixin, ListView):
    perfiles = (JEFATURA, TECNICO_INTERNO, TECNICO_EXTERNO)
    template_name = "inventario/lista.html"
    context_object_name = "equipos"
    paginate_by = 30

    def get_queryset(self):
        qs = equipos_visibles(self.request.user)
        g = self.request.GET
        if g.get("q"):
            q = g["q"].strip()
            qs = qs.filter(Q(codigo__icontains=q) | Q(nombre__icontains=q) | Q(marca__icontains=q) | Q(modelo__icontains=q))
        if g.get("categoria"):
            qs = qs.filter(categoria_id=g["categoria"]) if g["categoria"].isdigit() else qs.none()
        if g.get("estado") == "todos":
            pass
        elif g.get("estado") in {Equipo.ACTIVO, Equipo.EN_MANTENCION, Equipo.BAJA}:
            qs = qs.filter(estado=g["estado"])
        else:
            qs = qs.exclude(estado=Equipo.BAJA)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categorias"] = Categoria.objects.all()
        ctx["filtros"] = self.request.GET
        return ctx


@perfil_requerido(JEFATURA, TECNICO_INTERNO, TECNICO_EXTERNO)
def equipo_detalle(request, pk):
    from mantenciones.models import PlanMantencion, RegistroMantencion
    from tickets.models import Ticket

    equipo = equipo_o_403(request, pk)
    contexto = {
        "equipo": equipo,
        "versiones": equipo.versiones.all()[:20],
        "planes": PlanMantencion.objects.filter(equipo=equipo).select_related("plantilla"),
        "registros": RegistroMantencion.objects.filter(equipo=equipo).select_related("tecnico").order_by("-inicio")[:10],
        "tickets": Ticket.objects.filter(equipo=equipo).order_by("-fecha_creacion")[:10],
        "externos": equipo.tecnicos_externos.all(),
        "form_version": FormularioVersion(),
    }
    return render(request, "inventario/detalle.html", contexto)


@perfil_requerido(JEFATURA)
def equipo_nuevo(request):
    form = FormularioEquipo(request.POST or None, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        equipo = form.save()
        auditoria.registrar(request.user, auditoria.EQUIPO_CREADO, "equipo", equipo.pk, {"codigo": equipo.codigo}, request)
        messages.success(request, f"Equipo {equipo.codigo} registrado.")
        return redirect("inventario:detalle", pk=equipo.pk)
    return render(request, "inventario/form.html", {"form": form, "titulo": "Nuevo equipo"})


@perfil_requerido(JEFATURA)
def equipo_editar(request, pk):
    equipo = equipo_o_403(request, pk)
    if equipo.esta_de_baja:
        messages.error(request, "Un equipo dado de baja no se puede editar; su historial se conserva.")
        return redirect("inventario:detalle", pk=pk)
    form = FormularioEquipo(request.POST or None, instance=equipo, usuario=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        auditoria.registrar(request.user, auditoria.EQUIPO_EDITADO, "equipo", equipo.pk, {"campos": form.changed_data}, request)
        messages.success(request, "Equipo actualizado.")
        return redirect("inventario:detalle", pk=pk)
    return render(request, "inventario/form.html", {"form": form, "titulo": f"Editar {equipo.codigo}", "equipo": equipo})


@require_POST
@perfil_requerido(JEFATURA)
def equipo_baja(request, pk):
    equipo = equipo_o_403(request, pk)
    if not equipo.esta_de_baja:
        equipo.dar_de_baja()
        auditoria.registrar(request.user, auditoria.EQUIPO_BAJA, "equipo", equipo.pk, {"codigo": equipo.codigo}, request)
        messages.success(request, f"{equipo.codigo} fue dado de baja. Su historial se conserva.")
    return redirect("inventario:detalle", pk=pk)


@require_POST
@perfil_requerido(JEFATURA)
def version_nueva(request, pk):
    equipo = equipo_o_403(request, pk)
    form = FormularioVersion(request.POST)
    if form.is_valid():
        version = form.save(commit=False)
        version.equipo = equipo
        version.save()
        auditoria.registrar(
            request.user, auditoria.VERSION_SOFTWARE, "equipo", equipo.pk, {"tipo": version.tipo, "version": version.version}, request
        )
        messages.success(request, "Versión registrada en la hoja de vida.")
    else:
        errores = [mensaje for lista in form.errors.values() for mensaje in lista]
        messages.error(request, "No se pudo registrar la versión: " + "; ".join(errores))
    return redirect("inventario:detalle", pk=pk)

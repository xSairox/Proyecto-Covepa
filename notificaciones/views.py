from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from notificaciones.models import Notificacion


@login_required
def lista(request):
    avisos = Notificacion.objects.filter(usuario=request.user)[:100]
    return render(request, "notificaciones/lista.html", {"avisos": avisos})


@require_POST
@login_required
def marcar_leida(request, pk):
    aviso = get_object_or_404(Notificacion, pk=pk, usuario=request.user)  # solo los propios
    aviso.marcar_leida()
    destino = aviso.url if aviso.url.startswith("/") and not aviso.url.startswith("//") else "notificaciones:lista"
    return redirect(destino)


@require_POST
@login_required
def marcar_todas(request):
    Notificacion.objects.filter(usuario=request.user, leida=False).update(leida=True)
    return redirect("notificaciones:lista")

"""Datos comunes a todas las plantillas: navegación inferior por perfil y avisos sin leer (informe, 6.3)."""

from django.urls import NoReverseMatch, reverse

from core.permisos import AUDITOR, JEFATURA, TECNICO_EXTERNO, TECNICO_INTERNO, TRABAJADOR, codigo_perfil

# (texto, nombre de la ruta, ícono)
NAVEGACION = {
    JEFATURA: [
        ("Panel", "panel", "inicio"),
        ("Tickets", "tickets:lista", "ticket"),
        ("Equipos", "inventario:lista", "equipo"),
        ("Más", "mas", "menu"),
    ],
    TECNICO_INTERNO: [
        ("Inicio", "mantenciones:inicio", "inicio"),
        ("Equipos", "inventario:lista", "equipo"),
        ("Tickets", "tickets:lista", "ticket"),
        ("Historial", "mantenciones:historial", "historial"),
    ],
    TECNICO_EXTERNO: [
        ("Inicio", "mantenciones:inicio", "inicio"),
        ("Equipos", "inventario:lista", "equipo"),
        ("Tickets", "tickets:lista", "ticket"),
    ],
    TRABAJADOR: [
        ("Mis tickets", "tickets:lista", "ticket"),
        ("Reportar", "tickets:nuevo", "mas"),
    ],
    AUDITOR: [
        ("Auditoría", "auditoria:lista", "escudo"),
        ("Historial", "mantenciones:historial", "historial"),
    ],
}


def navegacion(request):
    usuario = getattr(request, "user", None)
    if usuario is None or not usuario.is_authenticated:
        return {}
    codigo = codigo_perfil(usuario)
    if usuario.perfil.requiere_dos_pasos and not request.session.get("otp_verificado"):
        return {"nav_items": [], "avisos_sin_leer": 0, "perfil_codigo": codigo}

    elementos = []
    for texto, ruta, icono in NAVEGACION.get(codigo, []):
        try:
            url = reverse(ruta)
        except NoReverseMatch:  # pragma: no cover
            continue
        elementos.append({"texto": texto, "url": url, "icono": icono, "activo": False})
    # Activo = el elemento cuya ruta coincide con el prefijo más largo de la ruta actual
    mejores = [(len(e["url"]), e) for e in elementos if request.path.startswith(e["url"])]
    if mejores:
        max(mejores, key=lambda par: par[0])[1]["activo"] = True

    from notificaciones.models import Notificacion

    return {
        "nav_items": elementos,
        "avisos_sin_leer": Notificacion.objects.filter(usuario=usuario, leida=False).count(),
        "perfil_codigo": codigo,
        "es_tecnico": codigo in (TECNICO_INTERNO, TECNICO_EXTERNO),
    }

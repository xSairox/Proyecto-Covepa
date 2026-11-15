from django import template

register = template.Library()

_TICKET = {
    "Pendiente": "alerta",
    "Aprobado": "curso",
    "En ejecución": "curso",
    "Realizado": "ok",
    "Cerrado": "neutro",
    "Rechazado": "vencido",
}
_EQUIPO = {"Activo": "ok", "En mantención": "curso", "Baja": "neutro"}


@register.simple_tag(takes_context=True)
def qs_sin_pagina(context):
    """Conserva los filtros de la URL al cambiar de página."""
    consulta = context["request"].GET.copy()
    consulta.pop("page", None)
    texto = consulta.urlencode()
    return f"&{texto}" if texto else ""


@register.filter
def tono_ticket(estado):
    return _TICKET.get(estado, "neutro")


@register.filter
def tono_equipo(estado):
    return _EQUIPO.get(estado, "neutro")


@register.filter
def tono_dias(dias):
    """Tono de un plan según los días que faltan: vencido, hoy o a tiempo."""
    try:
        dias = int(dias)
    except (TypeError, ValueError):
        return "neutro"
    if dias < 0:
        return "vencido"
    return "alerta" if dias <= 2 else "ok"


@register.filter
def texto_dias(dias):
    try:
        dias = int(dias)
    except (TypeError, ValueError):
        return ""
    if dias < 0:
        return f"Vencida hace {-dias} día{'s' if dias != -1 else ''}"
    if dias == 0:
        return "Vence hoy"
    return f"Vence en {dias} día{'s' if dias != 1 else ''}"


@register.filter
def con_clase(campo, clase):
    return campo.as_widget(attrs={"class": clase})

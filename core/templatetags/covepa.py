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


# --------------------------------------------------------------------------- textos legibles

_PERMISOS = {
    "usuarios.gestionar": "Crear, editar y desactivar usuarios",
    "equipos.gestionar": "Registrar, editar y dar de baja equipos",
    "plantillas.gestionar": "Diseñar los formularios de mantención",
    "planes.gestionar": "Programar mantenciones periódicas",
    "tickets.crear": "Reportar fallas y crear tickets",
    "tickets.aprobar": "Aprobar o rechazar tickets y asignar técnicos",
    "tickets.cerrar": "Revisar y cerrar trabajos realizados",
    "tickets.ejecutar": "Ejecutar los tickets que te asignan",
    "historial.ver": "Consultar el historial de mantenciones",
    "auditoria.ver": "Consultar la auditoría del sistema",
    "mantenciones.registrar": "Registrar mantenciones, también sin conexión",
    "equipos.ver_sucursal": "Ver los equipos de tu sucursal",
    "equipos.ver_asignados": "Ver los equipos que te asignaron",
}

_ACCIONES = {
    "login_ok": "Inicio de sesión",
    "login_fallido": "Intento de ingreso fallido",
    "cuenta_bloqueada": "Cuenta bloqueada",
    "dos_pasos_fallido": "Código de dos pasos incorrecto",
    "dos_pasos_activado": "Dos pasos activado",
    "logout": "Cierre de sesión",
    "acceso_denegado": "Acceso denegado",
    "usuario_creado": "Usuario creado",
    "usuario_editado": "Usuario editado",
    "usuario_desactivado": "Usuario desactivado",
    "contrasena_definida": "Contraseña definida",
    "equipo_creado": "Equipo registrado",
    "equipo_editado": "Equipo editado",
    "equipo_baja": "Equipo dado de baja",
    "version_software": "Versión de software",
    "plantilla_publicada": "Plantilla publicada",
    "plan_guardado": "Plan guardado",
    "mantencion_sincronizada": "Mantención recibida",
    "mantencion_duplicada": "Mantención duplicada (ignorada)",
    "mantencion_rechazada": "Mantención rechazada",
    "ticket_cambio_estado": "Cambio de estado de ticket",
}


@register.filter
def permiso_legible(codigo):
    return _PERMISOS.get(codigo, codigo)


@register.filter
def accion_legible(codigo):
    return _ACCIONES.get(codigo, str(codigo).replace("_", " ").capitalize())


@register.filter
def pesos(monto):
    """12345 -> $12.345 (formato chileno, sin depender de la configuración regional)."""
    try:
        return "$" + f"{int(monto):,}".replace(",", ".")
    except (TypeError, ValueError):
        return ""


@register.filter
def iniciales(usuario):
    nombre = (getattr(usuario, "nombre", "") or "").strip()
    apellido = (getattr(usuario, "apellido", "") or "").strip()
    return ((nombre[:1] + apellido[:1]) or "?").upper()

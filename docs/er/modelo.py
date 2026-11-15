"""Fuente única del modelo de datos: genera el diagrama ER (PNG y SVG) y el diccionario de datos.

    python docs/er/modelo.py        (requiere Graphviz: comando `dot`)

Si cambias un modelo de Django, actualiza aquí y vuelve a ejecutar."""

import subprocess
from pathlib import Path

AQUI = Path(__file__).parent
RAIZ = AQUI.parent

# (columna, tipo, clave, descripción)   clave: PK, FK, PK/FK, UK o ""
PG = {
    "perfil": ("Rol del sistema con sus permisos", "cuentas", [
        ("id_perfil", "SERIAL", "PK", "Identificador del perfil."),
        ("codigo", "VARCHAR(30)", "UK", "Código interno: jefatura, tecnico_interno, tecnico_externo, trabajador, auditor."),
        ("nombre", "VARCHAR(60)", "", "Nombre visible del perfil."),
        ("permisos", "JSONB", "", "Lista de permisos (ej. tickets.aprobar)."),
    ]),
    "usuario": ("Persona que usa el sistema. Se identifica por correo; no se guarda el RUT", "cuentas", [
        ("id_usuario", "SERIAL", "PK", "Identificador interno del usuario."),
        ("nombre", "VARCHAR(60)", "", "Nombres."),
        ("apellido", "VARCHAR(60)", "", "Apellidos."),
        ("correo", "VARCHAR(120)", "UK", "Correo con el que ingresa (único, en minúsculas)."),
        ("password", "VARCHAR(128)", "", "Contraseña con hash (nunca en texto plano)."),
        ("id_perfil", "INTEGER", "FK", "Perfil del usuario → perfil."),
        ("id_sucursal", "INTEGER", "FK", "Sucursal a la que pertenece (vacío en técnicos externos) → sucursal."),
        ("empresa_externa", "VARCHAR(100)", "", "Empresa del técnico externo."),
        ("is_active", "BOOLEAN", "", "Cuenta activa. Al desactivar se cierran sus sesiones."),
        ("dos_pasos_activo", "BOOLEAN", "", "Verificación en dos pasos configurada."),
        ("totp_secreto", "VARCHAR(200)", "", "Secreto TOTP cifrado."),
        ("intentos_fallidos", "SMALLINT", "", "Intentos de ingreso fallidos consecutivos."),
        ("bloqueado_hasta", "TIMESTAMPTZ", "", "Fin del bloqueo temporal (15 min tras 5 intentos)."),
        ("fecha_creacion", "TIMESTAMPTZ", "", "Alta de la cuenta."),
    ]),
    "token_acceso": ("Enlace de un solo uso para definir contraseña (invitación o recuperación)", "cuentas", [
        ("id_token", "SERIAL", "PK", "Identificador."),
        ("id_usuario", "INTEGER", "FK", "Dueño del enlace → usuario."),
        ("tipo", "VARCHAR(20)", "", "invitacion (24 h) o recuperacion (1 h)."),
        ("token_hash", "CHAR(64)", "UK", "SHA-256 del token; el token en claro solo viaja en el enlace."),
        ("creado", "TIMESTAMPTZ", "", "Emisión."),
        ("expira", "TIMESTAMPTZ", "", "Vencimiento."),
        ("usado", "TIMESTAMPTZ", "", "Momento en que se usó (vacío si sigue vigente)."),
    ]),
    "sucursal": ("Sucursal de COVEPA", "inventario", [
        ("id_sucursal", "SERIAL", "PK", "Identificador."),
        ("nombre", "VARCHAR(80)", "UK", "Nombre (ej. Fresia)."),
        ("comuna", "VARCHAR(80)", "", "Comuna."),
        ("prefijo", "VARCHAR(4)", "UK", "Prefijo para el código de equipo (ej. FRE)."),
    ]),
    "categoria": ("Tipo de equipo", "inventario", [
        ("id_categoria", "SERIAL", "PK", "Identificador."),
        ("nombre", "VARCHAR(80)", "UK", "Nombre (ej. Generador, UPS)."),
        ("prefijo", "VARCHAR(4)", "UK", "Prefijo para el código de equipo (ej. GEN)."),
    ]),
    "equipo": ("Equipo del inventario. No se elimina: se da de baja y conserva su historial", "inventario", [
        ("id_equipo", "SERIAL", "PK", "Identificador."),
        ("codigo", "VARCHAR(20)", "UK", "Código TIPO-SUC-00 (ej. GEN-FRE-01), generado automáticamente."),
        ("nombre", "VARCHAR(100)", "", "Nombre del equipo."),
        ("marca", "VARCHAR(60)", "", "Marca."),
        ("modelo", "VARCHAR(60)", "", "Modelo."),
        ("ubicacion", "VARCHAR(120)", "", "Ubicación física."),
        ("estado", "VARCHAR(20)", "", "Activo, En mantención o Baja."),
        ("id_categoria", "INTEGER", "FK", "Tipo de equipo → categoria."),
        ("id_sucursal", "INTEGER", "FK", "Sucursal donde está → sucursal."),
        ("fecha_alta", "DATE", "", "Fecha de incorporación al inventario."),
        ("fecha_baja", "DATE", "", "Fecha de baja (vacía si está en uso)."),
    ]),
    "equipo_tecnico_externo": ("Equipos que puede ver y mantener cada técnico externo", "inventario", [
        ("id", "SERIAL", "PK", "Identificador."),
        ("equipo_id", "INTEGER", "FK", "Equipo asignado → equipo."),
        ("usuario_id", "INTEGER", "FK", "Técnico externo → usuario."),
    ]),
    "version_software": ("Firmware o software instalado en un equipo, con su historial", "inventario", [
        ("id_version", "SERIAL", "PK", "Identificador."),
        ("id_equipo", "INTEGER", "FK", "Equipo → equipo."),
        ("tipo", "VARCHAR(10)", "", "firmware o software."),
        ("version", "VARCHAR(40)", "", "Número de versión."),
        ("fecha", "DATE", "", "Fecha de instalación."),
        ("actual", "BOOLEAN", "", "Es la versión vigente del equipo."),
    ]),
    "plantilla": ("Formulario de mantención por tipo de equipo. Sus campos viven en MongoDB, versionados", "mantenciones", [
        ("id_plantilla", "SERIAL", "PK", "Identificador."),
        ("nombre", "VARCHAR(120)", "UK", "Nombre; único dentro de la categoría."),
        ("id_categoria", "INTEGER", "FK", "Tipo de equipo al que aplica → categoria."),
        ("activa", "BOOLEAN", "", "Disponible para registrar mantenciones."),
        ("version_actual", "INTEGER", "", "Número de la versión vigente en MongoDB (0 = sin publicar)."),
    ]),
    "plan_mantencion": ("Mantención periódica programada para un equipo", "mantenciones", [
        ("id_plan", "SERIAL", "PK", "Identificador."),
        ("id_equipo", "INTEGER", "FK", "Equipo → equipo."),
        ("id_plantilla", "INTEGER", "FK", "Formulario que se usa → plantilla."),
        ("actividad", "VARCHAR(120)", "", "Descripción (ej. Prueba semanal de arranque)."),
        ("frecuencia_dias", "INTEGER", "", "Cada cuántos días se repite."),
        ("duracion_min", "INTEGER", "", "Duración estimada."),
        ("ultima_fecha", "DATE", "", "Última vez realizada (la próxima = última + frecuencia)."),
        ("fecha_creacion", "DATE", "", "Creación del plan."),
        ("activo", "BOOLEAN", "", "Plan vigente."),
    ]),
    "registro_mantencion": ("Datos para filtrar de cada mantención; el formulario completo está en MongoDB con el mismo UUID", "mantenciones", [
        ("id_documento", "UUID", "PK", "Generado en el celular; es también el _id del documento en MongoDB."),
        ("id_equipo", "INTEGER", "FK", "Equipo mantenido → equipo."),
        ("id_tecnico", "INTEGER", "FK", "Técnico que lo realizó → usuario."),
        ("id_plantilla", "INTEGER", "FK", "Formulario usado → plantilla."),
        ("version_plantilla", "INTEGER", "", "Versión de la plantilla que se respondió."),
        ("id_plan", "INTEGER", "FK", "Plan que se cumplió (opcional) → plan_mantencion."),
        ("inicio", "TIMESTAMPTZ", "", "Inicio (hora del celular)."),
        ("termino", "TIMESTAMPTZ", "", "Término."),
        ("estado_sync", "VARCHAR(15)", "", "pendiente, sincronizado o error."),
        ("origen", "VARCHAR(30)", "", "app_movil, app_movil_sin_conexion o web."),
        ("sincronizado_en", "TIMESTAMPTZ", "", "Cuándo llegó al servidor."),
    ]),
    "ticket": ("Mantención correctiva o reporte de falla, con su flujo de aprobación", "tickets", [
        ("id_ticket", "SERIAL", "PK", "Identificador (se muestra como T-00012)."),
        ("tipo", "VARCHAR(15)", "", "falla, correctiva o solicitud."),
        ("descripcion", "TEXT", "", "Qué ocurrió."),
        ("estado", "VARCHAR(20)", "", "Pendiente, Aprobado, En ejecución, Realizado, Cerrado o Rechazado."),
        ("id_equipo", "INTEGER", "FK", "Equipo afectado (opcional) → equipo."),
        ("id_solicitante", "INTEGER", "FK", "Quien lo reportó → usuario."),
        ("id_tecnico", "INTEGER", "FK", "Técnico asignado → usuario."),
        ("fecha_creacion", "TIMESTAMPTZ", "", "Creación."),
        ("inicio_trabajo", "TIMESTAMPTZ", "", "Cuándo el técnico inició."),
        ("termino_trabajo", "TIMESTAMPTZ", "", "Cuándo el técnico terminó."),
        ("motivo_rechazo", "VARCHAR(300)", "", "Motivo, si fue rechazado."),
    ]),
    "historial_estado": ("Cada cambio de estado de un ticket (composición: no existe sin su ticket)", "tickets", [
        ("id_historial", "SERIAL", "PK", "Identificador."),
        ("id_ticket", "INTEGER", "FK", "Ticket → ticket."),
        ("estado", "VARCHAR(20)", "", "Estado al que pasó."),
        ("fecha", "TIMESTAMPTZ", "", "Momento del cambio."),
        ("observacion", "VARCHAR(300)", "", "Motivo u observación."),
        ("id_usuario", "INTEGER", "FK", "Quién lo cambió → usuario."),
    ]),
    "material": ("Material usado en un ticket", "tickets", [
        ("id_material", "SERIAL", "PK", "Identificador."),
        ("id_ticket", "INTEGER", "FK", "Ticket → ticket."),
        ("descripcion", "VARCHAR(120)", "", "Qué material."),
        ("cantidad", "NUMERIC(10,2)", "", "Cantidad (mayor que 0)."),
        ("unidad", "VARCHAR(20)", "", "Unidad (u, m, L…)."),
    ]),
    "documento_respaldo": ("Factura o guía de despacho de un ticket; solo guarda la URL de la foto", "tickets", [
        ("id_documento_respaldo", "SERIAL", "PK", "Identificador."),
        ("id_ticket", "INTEGER", "FK", "Ticket → ticket."),
        ("tipo", "VARCHAR(15)", "", "factura, guia_despacho u otro."),
        ("numero", "VARCHAR(30)", "", "Número del documento."),
        ("proveedor", "VARCHAR(100)", "", "Proveedor."),
        ("monto", "INTEGER", "", "Monto en pesos chilenos."),
        ("url_foto", "VARCHAR(255)", "", "URL de la foto en Cloudinary."),
    ]),
    "notificacion": ("Aviso para un usuario (vencimientos, tickets por aprobar o asignados)", "notificaciones", [
        ("id_notificacion", "SERIAL", "PK", "Identificador."),
        ("id_usuario", "INTEGER", "FK", "Destinatario → usuario."),
        ("texto", "VARCHAR(200)", "", "Mensaje."),
        ("url", "VARCHAR(200)", "", "Pantalla a la que lleva."),
        ("clave", "VARCHAR(80)", "UK", "Evita repetir el mismo aviso (único por usuario)."),
        ("fecha", "TIMESTAMPTZ", "", "Creación."),
        ("leida", "BOOLEAN", "", "Ya fue leída."),
    ]),
    "auditoria": ("Registro de solo inserción de acciones sensibles (no se edita ni se borra)", "auditoria", [
        ("id_auditoria", "BIGSERIAL", "PK", "Identificador."),
        ("fecha", "TIMESTAMPTZ", "", "Momento del evento."),
        ("id_usuario", "INTEGER", "FK", "Quién actuó (vacío en ingresos con correo inexistente) → usuario."),
        ("accion", "VARCHAR(40)", "", "login_ok, acceso_denegado, ticket_cambio_estado…"),
        ("entidad", "VARCHAR(60)", "", "Tabla o recurso afectado."),
        ("entidad_id", "VARCHAR(64)", "", "Identificador del recurso."),
        ("detalle", "JSONB", "", "Datos del evento."),
        ("ip", "INET", "", "Dirección IP de origen."),
    ]),
}

MONGO = {
    "formularios_mantencion": ("Formulario completo de cada mantención (respuestas y evidencias)", [
        ("_id", "UUID (string)", "PK", "Mismo UUID que registro_mantencion.id_documento."),
        ("equipo", "objeto", "", "{codigo, categoria}."),
        ("sucursal", "string", "", "Nombre de la sucursal."),
        ("plantilla", "objeto", "", "{id, nombre, version} de la plantilla respondida."),
        ("tecnico_id", "int", "FK", "→ usuario.id_usuario (PostgreSQL)."),
        ("inicio / termino", "fecha", "", "Inicio y término."),
        ("respuestas", "objeto", "", "Clave de campo → valor (número, sí/no, texto, opción)."),
        ("evidencias", "arreglo", "", "[{campo, tipo, url, public_id, peso_kb, duracion_seg}]: solo URL de Cloudinary."),
        ("origen / estado", "string", "", "app_movil, app_movil_sin_conexion o web · sincronizado."),
        ("plan_id", "int", "FK", "→ plan_mantencion (opcional)."),
        ("recibido_en", "fecha", "", "Cuándo llegó al servidor."),
    ]),
    "versiones_plantilla": ("Campos de cada versión publicada de una plantilla (las versiones no se modifican)", [
        ("_id", "ObjectId", "PK", "Identificador."),
        ("plantilla_id", "int", "FK", "→ plantilla.id_plantilla (PostgreSQL). Índice único (plantilla_id, numero)."),
        ("nombre", "string", "", "Nombre de la plantilla al publicar."),
        ("numero", "int", "", "Versión 1, 2, 3…"),
        ("fecha", "fecha", "", "Publicación."),
        ("campos", "arreglo", "", "[{clave, etiqueta, tipo, obligatorio, opciones, min, max, unidad, mayor_que}]."),
    ]),
}

# (origen, columna, destino, etiqueta)
RELACIONES = [
    ("usuario", "perfil", "N:1"), ("usuario", "sucursal", "N:1"), ("token_acceso", "usuario", "N:1"),
    ("equipo", "categoria", "N:1"), ("equipo", "sucursal", "N:1"),
    ("equipo_tecnico_externo", "equipo", "N:1"), ("equipo_tecnico_externo", "usuario", "N:1"),
    ("version_software", "equipo", "N:1"), ("plantilla", "categoria", "N:1"),
    ("plan_mantencion", "equipo", "N:1"), ("plan_mantencion", "plantilla", "N:1"),
    ("registro_mantencion", "equipo", "N:1"), ("registro_mantencion", "usuario", "N:1"),
    ("registro_mantencion", "plantilla", "N:1"), ("registro_mantencion", "plan_mantencion", "N:1"),
    ("ticket", "equipo", "N:1"), ("ticket", "usuario", "solicitante"), ("ticket", "usuario", "técnico"),
    ("historial_estado", "ticket", "N:1"), ("material", "ticket", "N:1"), ("documento_respaldo", "ticket", "N:1"),
    ("historial_estado", "usuario", "N:1"), ("notificacion", "usuario", "N:1"), ("auditoria", "usuario", "N:1"),
]
# Vínculos lógicos entre bases (no son claves foráneas reales)
ENTRE_BASES = [
    ("registro_mantencion", "formularios_mantencion", "mismo UUID"),
    ("plantilla", "versiones_plantilla", "plantilla_id + versión"),
]

COLOR = {"cuentas": "#FEE101", "inventario": "#FFFFFF", "mantenciones": "#FFFFFF", "tickets": "#FFFFFF", "notificaciones": "#FFFFFF", "auditoria": "#FFFFFF"}
ROJO, GRIS, TINTA = "#E10003", "#5F5A4B", "#1D1B16"


def _fila(c, t, k, _descripcion=""):
    marca = {"PK": "PK", "FK": "FK", "PK/FK": "PK FK", "UK": "UK", "": ""}[k]
    estilo = "<B>" if "PK" in marca else ""
    cierre = "</B>" if "PK" in marca else ""
    cmarca = f'<FONT COLOR="{ROJO}"><B>{marca}</B></FONT>' if marca else ""
    return (f'<TR><TD ALIGN="LEFT" WIDTH="34">{cmarca}</TD><TD ALIGN="LEFT">{estilo}{c}{cierre}</TD>'
            f'<TD ALIGN="LEFT"><FONT COLOR="{GRIS}">{t}</FONT></TD></TR>')


def dot():
    out = ['digraph ER {', 'graph [rankdir=LR, splines=polyline, nodesep=0.35, ranksep=1.1, fontname="Helvetica", pad=0.4, bgcolor="white", '
           'label=<<FONT POINT-SIZE="22"><B>COVEPA Mantenciones · Modelo entidad-relación</B></FONT><BR/><FONT POINT-SIZE="13" COLOR="' + GRIS +
           '">PostgreSQL (Neon) en amarillo · MongoDB Atlas en rojo · Cloudinary guarda solo las URL</FONT>>, labelloc=t];',
           'node [shape=plaintext, fontname="Helvetica", fontsize=11];', f'edge [color="{GRIS}", arrowsize=0.7, penwidth=1.1, fontname="Helvetica", fontsize=9];']
    for nombre, (_desc, app, cols) in PG.items():
        fondo = "#FEE101" if app == "cuentas" else "#FFF6B3"
        filas = "".join(_fila(*c) for c in cols)
        out.append(f'"{nombre}" [label=<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="3" COLOR="{TINTA}">'
                   f'<TR><TD COLSPAN="3" BGCOLOR="{fondo}"><B>{nombre}</B></TD></TR>{filas}</TABLE>>];')
    for nombre, (_desc, cols) in MONGO.items():
        filas = "".join(_fila(*c) for c in cols)
        out.append(f'"{nombre}" [label=<<TABLE BORDER="2" CELLBORDER="0" CELLSPACING="0" CELLPADDING="3" COLOR="{ROJO}">'
                   f'<TR><TD COLSPAN="3" BGCOLOR="{ROJO}"><FONT COLOR="white"><B>{nombre}</B> (MongoDB)</FONT></TD></TR>{filas}</TABLE>>];')
    for o, d, _et in RELACIONES:  # pata de gallo en el lado «muchos» (origen), barra en el lado «uno» (destino)
        out.append(f'"{o}" -> "{d}" [dir=both, arrowtail=crowtee, arrowhead=teetee];')
    for o, d, et in ENTRE_BASES:
        out.append(f'"{o}" -> "{d}" [style=dashed, color="{ROJO}", fontcolor="{ROJO}", label="{et}", arrowhead=none];')
    out.append('}')
    return "\n".join(out)


def diccionario():
    t = ["# Diccionario de datos · COVEPA Mantenciones", "",
         "Generado desde `docs/er/modelo.py` (misma fuente que el diagrama ER). Claves: **PK** primaria, **FK** foránea, **UK** única.", "",
         "## Resumen de entidades", "", "| Base | Entidad | Para qué sirve |", "|---|---|---|"]
    for n, (d, _a, _c) in PG.items():
        t.append(f"| PostgreSQL (Neon) | `{n}` | {d}. |")
    for n, (d, _c) in MONGO.items():
        t.append(f"| MongoDB Atlas | `{n}` | {d}. |")
    t += ["", "Las fotos y los videos **no** se guardan en ninguna base: viven en Cloudinary y las bases solo guardan su URL.", ""]
    for n, (d, app, cols) in PG.items():
        t += [f"## `{n}`", "", f"{d}. (Aplicación Django: `{app}`.)", "", "| Atributo | Tipo de dato | Clave | Descripción |", "|---|---|---|---|"]
        t += [f"| `{c}` | {ty} | {k} | {ds} |" for c, ty, k, ds in cols]
        t.append("")
    for n, (d, cols) in MONGO.items():
        t += [f"## `{n}` (MongoDB)", "", f"{d}.", "", "| Atributo | Tipo de dato | Clave | Descripción |", "|---|---|---|---|"]
        t += [f"| `{c}` | {ty} | {k} | {ds} |" for c, ty, k, ds in cols]
        t.append("")
    t += ["## Reglas de integridad", "",
          "- Los equipos, usuarios y registros **no se eliminan** (claves foráneas con `PROTECT`): se dan de baja o se desactivan y conservan su historial.",
          "- `historial_estado`, `material` y `documento_respaldo` se eliminan junto con su ticket (composición).",
          "- `auditoria` es de solo inserción: la aplicación bloquea `UPDATE`/`DELETE` y, en PostgreSQL, un trigger los rechaza.",
          "- No hay transacción entre PostgreSQL y MongoDB: la sincronización inserta primero en MongoDB (idempotente por `_id`) y, si PostgreSQL falla, borra ese documento. `python manage.py verificar_integridad` comprueba que ambas bases coincidan.", ""]
    return "\n".join(t)


if __name__ == "__main__":
    fuente = AQUI / "er.dot"
    fuente.write_text(dot(), encoding="utf-8")
    for formato, extra in (("svg", []), ("png", ["-Gdpi=130"])):
        subprocess.run(["dot", f"-T{formato}", *extra, str(fuente), "-o", str(AQUI / f"diagrama_er.{formato}")], check=True)
    (RAIZ / "diccionario_datos.md").write_text(diccionario(), encoding="utf-8")
    print("Listo: diagrama_er.svg, diagrama_er.png y docs/diccionario_datos.md")

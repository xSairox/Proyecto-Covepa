# Diccionario de datos · COVEPA Mantenciones

Generado desde `docs/er/modelo.py` (misma fuente que el diagrama ER). Claves: **PK** primaria, **FK** foránea, **UK** única.

## Resumen de entidades

| Base | Entidad | Para qué sirve |
|---|---|---|
| PostgreSQL (Neon) | `perfil` | Rol del sistema con sus permisos. |
| PostgreSQL (Neon) | `usuario` | Persona que usa el sistema. Se identifica por correo; no se guarda el RUT. |
| PostgreSQL (Neon) | `token_acceso` | Enlace de un solo uso para definir contraseña (invitación o recuperación). |
| PostgreSQL (Neon) | `sucursal` | Sucursal de COVEPA. |
| PostgreSQL (Neon) | `categoria` | Tipo de equipo. |
| PostgreSQL (Neon) | `equipo` | Equipo del inventario. No se elimina: se da de baja y conserva su historial. |
| PostgreSQL (Neon) | `equipo_tecnico_externo` | Equipos que puede ver y mantener cada técnico externo. |
| PostgreSQL (Neon) | `version_software` | Firmware o software instalado en un equipo, con su historial. |
| PostgreSQL (Neon) | `plantilla` | Formulario de mantención por tipo de equipo. Sus campos viven en MongoDB, versionados. |
| PostgreSQL (Neon) | `plan_mantencion` | Mantención periódica programada para un equipo. |
| PostgreSQL (Neon) | `registro_mantencion` | Datos para filtrar de cada mantención; el formulario completo está en MongoDB con el mismo UUID. |
| PostgreSQL (Neon) | `ticket` | Mantención correctiva o reporte de falla, con su flujo de aprobación. |
| PostgreSQL (Neon) | `historial_estado` | Cada cambio de estado de un ticket (composición: no existe sin su ticket). |
| PostgreSQL (Neon) | `material` | Material usado en un ticket. |
| PostgreSQL (Neon) | `documento_respaldo` | Factura o guía de despacho de un ticket; solo guarda la URL de la foto. |
| PostgreSQL (Neon) | `notificacion` | Aviso para un usuario (vencimientos, tickets por aprobar o asignados). |
| PostgreSQL (Neon) | `auditoria` | Registro de solo inserción de acciones sensibles (no se edita ni se borra). |
| MongoDB Atlas | `formularios_mantencion` | Formulario completo de cada mantención (respuestas y evidencias). |
| MongoDB Atlas | `versiones_plantilla` | Campos de cada versión publicada de una plantilla (las versiones no se modifican). |

Las fotos y los videos **no** se guardan en ninguna base: viven en Cloudinary y las bases solo guardan su URL.

## `perfil`

Rol del sistema con sus permisos. (Aplicación Django: `cuentas`.)

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `id_perfil` | SERIAL | PK | Identificador del perfil. |
| `codigo` | VARCHAR(30) | UK | Código interno: jefatura, tecnico_interno, tecnico_externo, trabajador, auditor. |
| `nombre` | VARCHAR(60) |  | Nombre visible del perfil. |
| `permisos` | JSONB |  | Lista de permisos (ej. tickets.aprobar). |

## `usuario`

Persona que usa el sistema. Se identifica por correo; no se guarda el RUT. (Aplicación Django: `cuentas`.)

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `id_usuario` | SERIAL | PK | Identificador interno del usuario. |
| `nombre` | VARCHAR(60) |  | Nombres. |
| `apellido` | VARCHAR(60) |  | Apellidos. |
| `correo` | VARCHAR(120) | UK | Correo con el que ingresa (único, en minúsculas). |
| `password` | VARCHAR(128) |  | Contraseña con hash (nunca en texto plano). |
| `id_perfil` | INTEGER | FK | Perfil del usuario → perfil. |
| `id_sucursal` | INTEGER | FK | Sucursal a la que pertenece (vacío en técnicos externos) → sucursal. |
| `empresa_externa` | VARCHAR(100) |  | Empresa del técnico externo. |
| `is_active` | BOOLEAN |  | Cuenta activa. Al desactivar se cierran sus sesiones. |
| `dos_pasos_activo` | BOOLEAN |  | Verificación en dos pasos configurada. |
| `totp_secreto` | VARCHAR(200) |  | Secreto TOTP cifrado. |
| `intentos_fallidos` | SMALLINT |  | Intentos de ingreso fallidos consecutivos. |
| `bloqueado_hasta` | TIMESTAMPTZ |  | Fin del bloqueo temporal (15 min tras 5 intentos). |
| `fecha_creacion` | TIMESTAMPTZ |  | Alta de la cuenta. |

## `token_acceso`

Enlace de un solo uso para definir contraseña (invitación o recuperación). (Aplicación Django: `cuentas`.)

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `id_token` | SERIAL | PK | Identificador. |
| `id_usuario` | INTEGER | FK | Dueño del enlace → usuario. |
| `tipo` | VARCHAR(20) |  | invitacion (24 h) o recuperacion (1 h). |
| `token_hash` | CHAR(64) | UK | SHA-256 del token; el token en claro solo viaja en el enlace. |
| `creado` | TIMESTAMPTZ |  | Emisión. |
| `expira` | TIMESTAMPTZ |  | Vencimiento. |
| `usado` | TIMESTAMPTZ |  | Momento en que se usó (vacío si sigue vigente). |

## `sucursal`

Sucursal de COVEPA. (Aplicación Django: `inventario`.)

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `id_sucursal` | SERIAL | PK | Identificador. |
| `nombre` | VARCHAR(80) | UK | Nombre (ej. Fresia). |
| `comuna` | VARCHAR(80) |  | Comuna. |
| `prefijo` | VARCHAR(4) | UK | Prefijo para el código de equipo (ej. FRE). |

## `categoria`

Tipo de equipo. (Aplicación Django: `inventario`.)

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `id_categoria` | SERIAL | PK | Identificador. |
| `nombre` | VARCHAR(80) | UK | Nombre (ej. Generador, UPS). |
| `prefijo` | VARCHAR(4) | UK | Prefijo para el código de equipo (ej. GEN). |

## `equipo`

Equipo del inventario. No se elimina: se da de baja y conserva su historial. (Aplicación Django: `inventario`.)

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `id_equipo` | SERIAL | PK | Identificador. |
| `codigo` | VARCHAR(20) | UK | Código TIPO-SUC-00 (ej. GEN-FRE-01), generado automáticamente. |
| `nombre` | VARCHAR(100) |  | Nombre del equipo. |
| `marca` | VARCHAR(60) |  | Marca. |
| `modelo` | VARCHAR(60) |  | Modelo. |
| `ubicacion` | VARCHAR(120) |  | Ubicación física. |
| `estado` | VARCHAR(20) |  | Activo, En mantención o Baja. |
| `id_categoria` | INTEGER | FK | Tipo de equipo → categoria. |
| `id_sucursal` | INTEGER | FK | Sucursal donde está → sucursal. |
| `fecha_alta` | DATE |  | Fecha de incorporación al inventario. |
| `fecha_baja` | DATE |  | Fecha de baja (vacía si está en uso). |

## `equipo_tecnico_externo`

Equipos que puede ver y mantener cada técnico externo. (Aplicación Django: `inventario`.)

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `id` | SERIAL | PK | Identificador. |
| `equipo_id` | INTEGER | FK | Equipo asignado → equipo. |
| `usuario_id` | INTEGER | FK | Técnico externo → usuario. |

## `version_software`

Firmware o software instalado en un equipo, con su historial. (Aplicación Django: `inventario`.)

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `id_version` | SERIAL | PK | Identificador. |
| `id_equipo` | INTEGER | FK | Equipo → equipo. |
| `tipo` | VARCHAR(10) |  | firmware o software. |
| `version` | VARCHAR(40) |  | Número de versión. |
| `fecha` | DATE |  | Fecha de instalación. |
| `actual` | BOOLEAN |  | Es la versión vigente del equipo. |

## `plantilla`

Formulario de mantención por tipo de equipo. Sus campos viven en MongoDB, versionados. (Aplicación Django: `mantenciones`.)

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `id_plantilla` | SERIAL | PK | Identificador. |
| `nombre` | VARCHAR(120) | UK | Nombre; único dentro de la categoría. |
| `id_categoria` | INTEGER | FK | Tipo de equipo al que aplica → categoria. |
| `activa` | BOOLEAN |  | Disponible para registrar mantenciones. |
| `version_actual` | INTEGER |  | Número de la versión vigente en MongoDB (0 = sin publicar). |

## `plan_mantencion`

Mantención periódica programada para un equipo. (Aplicación Django: `mantenciones`.)

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `id_plan` | SERIAL | PK | Identificador. |
| `id_equipo` | INTEGER | FK | Equipo → equipo. |
| `id_plantilla` | INTEGER | FK | Formulario que se usa → plantilla. |
| `actividad` | VARCHAR(120) |  | Descripción (ej. Prueba semanal de arranque). |
| `frecuencia_dias` | INTEGER |  | Cada cuántos días se repite. |
| `duracion_min` | INTEGER |  | Duración estimada. |
| `ultima_fecha` | DATE |  | Última vez realizada (la próxima = última + frecuencia). |
| `fecha_creacion` | DATE |  | Creación del plan. |
| `activo` | BOOLEAN |  | Plan vigente. |

## `registro_mantencion`

Datos para filtrar de cada mantención; el formulario completo está en MongoDB con el mismo UUID. (Aplicación Django: `mantenciones`.)

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `id_documento` | UUID | PK | Generado en el celular; es también el _id del documento en MongoDB. |
| `id_equipo` | INTEGER | FK | Equipo mantenido → equipo. |
| `id_tecnico` | INTEGER | FK | Técnico que lo realizó → usuario. |
| `id_plantilla` | INTEGER | FK | Formulario usado → plantilla. |
| `version_plantilla` | INTEGER |  | Versión de la plantilla que se respondió. |
| `id_plan` | INTEGER | FK | Plan que se cumplió (opcional) → plan_mantencion. |
| `inicio` | TIMESTAMPTZ |  | Inicio (hora del celular). |
| `termino` | TIMESTAMPTZ |  | Término. |
| `estado_sync` | VARCHAR(15) |  | pendiente, sincronizado o error. |
| `origen` | VARCHAR(30) |  | app_movil, app_movil_sin_conexion o web. |
| `sincronizado_en` | TIMESTAMPTZ |  | Cuándo llegó al servidor. |

## `ticket`

Mantención correctiva o reporte de falla, con su flujo de aprobación. (Aplicación Django: `tickets`.)

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `id_ticket` | SERIAL | PK | Identificador (se muestra como T-00012). |
| `tipo` | VARCHAR(15) |  | falla, correctiva o solicitud. |
| `descripcion` | TEXT |  | Qué ocurrió. |
| `estado` | VARCHAR(20) |  | Pendiente, Aprobado, En ejecución, Realizado, Cerrado o Rechazado. |
| `id_equipo` | INTEGER | FK | Equipo afectado (opcional) → equipo. |
| `id_solicitante` | INTEGER | FK | Quien lo reportó → usuario. |
| `id_tecnico` | INTEGER | FK | Técnico asignado → usuario. |
| `fecha_creacion` | TIMESTAMPTZ |  | Creación. |
| `inicio_trabajo` | TIMESTAMPTZ |  | Cuándo el técnico inició. |
| `termino_trabajo` | TIMESTAMPTZ |  | Cuándo el técnico terminó. |
| `motivo_rechazo` | VARCHAR(300) |  | Motivo, si fue rechazado. |

## `historial_estado`

Cada cambio de estado de un ticket (composición: no existe sin su ticket). (Aplicación Django: `tickets`.)

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `id_historial` | SERIAL | PK | Identificador. |
| `id_ticket` | INTEGER | FK | Ticket → ticket. |
| `estado` | VARCHAR(20) |  | Estado al que pasó. |
| `fecha` | TIMESTAMPTZ |  | Momento del cambio. |
| `observacion` | VARCHAR(300) |  | Motivo u observación. |
| `id_usuario` | INTEGER | FK | Quién lo cambió → usuario. |

## `material`

Material usado en un ticket. (Aplicación Django: `tickets`.)

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `id_material` | SERIAL | PK | Identificador. |
| `id_ticket` | INTEGER | FK | Ticket → ticket. |
| `descripcion` | VARCHAR(120) |  | Qué material. |
| `cantidad` | NUMERIC(10,2) |  | Cantidad (mayor que 0). |
| `unidad` | VARCHAR(20) |  | Unidad (u, m, L…). |

## `documento_respaldo`

Factura o guía de despacho de un ticket; solo guarda la URL de la foto. (Aplicación Django: `tickets`.)

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `id_documento_respaldo` | SERIAL | PK | Identificador. |
| `id_ticket` | INTEGER | FK | Ticket → ticket. |
| `tipo` | VARCHAR(15) |  | factura, guia_despacho u otro. |
| `numero` | VARCHAR(30) |  | Número del documento. |
| `proveedor` | VARCHAR(100) |  | Proveedor. |
| `monto` | INTEGER |  | Monto en pesos chilenos. |
| `url_foto` | VARCHAR(255) |  | URL de la foto en Cloudinary. |

## `notificacion`

Aviso para un usuario (vencimientos, tickets por aprobar o asignados). (Aplicación Django: `notificaciones`.)

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `id_notificacion` | SERIAL | PK | Identificador. |
| `id_usuario` | INTEGER | FK | Destinatario → usuario. |
| `texto` | VARCHAR(200) |  | Mensaje. |
| `url` | VARCHAR(200) |  | Pantalla a la que lleva. |
| `clave` | VARCHAR(80) | UK | Evita repetir el mismo aviso (único por usuario). |
| `fecha` | TIMESTAMPTZ |  | Creación. |
| `leida` | BOOLEAN |  | Ya fue leída. |

## `auditoria`

Registro de solo inserción de acciones sensibles (no se edita ni se borra). (Aplicación Django: `auditoria`.)

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `id_auditoria` | BIGSERIAL | PK | Identificador. |
| `fecha` | TIMESTAMPTZ |  | Momento del evento. |
| `id_usuario` | INTEGER | FK | Quién actuó (vacío en ingresos con correo inexistente) → usuario. |
| `accion` | VARCHAR(40) |  | login_ok, acceso_denegado, ticket_cambio_estado… |
| `entidad` | VARCHAR(60) |  | Tabla o recurso afectado. |
| `entidad_id` | VARCHAR(64) |  | Identificador del recurso. |
| `detalle` | JSONB |  | Datos del evento. |
| `ip` | INET |  | Dirección IP de origen. |

## `formularios_mantencion` (MongoDB)

Formulario completo de cada mantención (respuestas y evidencias).

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `_id` | UUID (string) | PK | Mismo UUID que registro_mantencion.id_documento. |
| `equipo` | objeto |  | {codigo, categoria}. |
| `sucursal` | string |  | Nombre de la sucursal. |
| `plantilla` | objeto |  | {id, nombre, version} de la plantilla respondida. |
| `tecnico_id` | int | FK | → usuario.id_usuario (PostgreSQL). |
| `inicio / termino` | fecha |  | Inicio y término. |
| `respuestas` | objeto |  | Clave de campo → valor (número, sí/no, texto, opción). |
| `evidencias` | arreglo |  | [{campo, tipo, url, public_id, peso_kb, duracion_seg}]: solo URL de Cloudinary. |
| `origen / estado` | string |  | app_movil, app_movil_sin_conexion o web · sincronizado. |
| `plan_id` | int | FK | → plan_mantencion (opcional). |
| `recibido_en` | fecha |  | Cuándo llegó al servidor. |

## `versiones_plantilla` (MongoDB)

Campos de cada versión publicada de una plantilla (las versiones no se modifican).

| Atributo | Tipo de dato | Clave | Descripción |
|---|---|---|---|
| `_id` | ObjectId | PK | Identificador. |
| `plantilla_id` | int | FK | → plantilla.id_plantilla (PostgreSQL). Índice único (plantilla_id, numero). |
| `nombre` | string |  | Nombre de la plantilla al publicar. |
| `numero` | int |  | Versión 1, 2, 3… |
| `fecha` | fecha |  | Publicación. |
| `campos` | arreglo |  | [{clave, etiqueta, tipo, obligatorio, opciones, min, max, unidad, mayor_que}]. |

## Reglas de integridad

- Los equipos, usuarios y registros **no se eliminan** (claves foráneas con `PROTECT`): se dan de baja o se desactivan y conservan su historial.
- `historial_estado`, `material` y `documento_respaldo` se eliminan junto con su ticket (composición).
- `auditoria` es de solo inserción: la aplicación bloquea `UPDATE`/`DELETE` y, en PostgreSQL, un trigger los rechaza.
- No hay transacción entre PostgreSQL y MongoDB: la sincronización inserta primero en MongoDB (idempotente por `_id`) y, si PostgreSQL falla, borra ese documento. `python manage.py verificar_integridad` comprueba que ambas bases coincidan.

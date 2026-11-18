# Protocolo de pruebas · COVEPA Mantenciones

Texto y tablas listos para pegar en el informe, **sección 9 (Plan de pruebas)**.
Las columnas «Resultado obtenido» y «Estado» se completan al ejecutar las pruebas (adjunta capturas para la Figura 12).

## 9.1 Estrategia de pruebas

Se combinan tres niveles. Las pruebas **automáticas** (Django `TestCase` y `unittest`) validan las reglas de negocio y la seguridad en cada cambio, sin red: MongoDB y Cloudinary se reemplazan por dobles en memoria. Las pruebas **de carga** (Locust) miden el tiempo de respuesta con técnicos simultáneos contra un entorno de prueba en Vercel. Las pruebas **manuales** en un celular real cubren lo que no se puede automatizar: instalación de la PWA, cámara y uso sin señal.

Cada caso parte de datos de demostración (`python manage.py seed_demo`) y se registra con su resultado esperado y el obtenido.

## 9.2 Casos de prueba

| ID | Tipo | Descripción | Herramienta | Modo | Resultado esperado | Estado |
|---|---|---|---|---|---|---|
| CP01 | Funcional | Crear un usuario con un correo ya registrado (también con otras mayúsculas). | Django TestCase | Automática | El sistema rechaza el segundo usuario con un mensaje en el campo correo; queda un solo usuario. | |
| CP02 | Integración | Enviar dos veces el mismo formulario de mantención (simula mala señal). | Django TestCase · Postman | Automática / manual | Primer envío 201, segundo 200 «duplicado». Un solo registro en PostgreSQL y un solo documento en MongoDB. Si PostgreSQL falla, no queda un documento huérfano en MongoDB. | |
| CP03 | Rendimiento | 20 técnicos simultáneos descargan su paquete y sincronizan formularios durante 3 minutos. | Locust | Automática | Sin errores 5xx; tiempo de respuesta del percentil 95 bajo 2 s en `/api/v1/paquete/` y bajo 3 s en la sincronización. | |
| CP04 | Usabilidad | Un técnico registra una prueba semanal de generador en un celular Android real, con guantes de trabajo y luz de día. | Celular real (Chrome) | Manual | Lo completa sin ayuda en menos de 3 minutos; botones de 48 px alcanzables; la cámara abre directo. | |
| CP05 | Funcional | Registrar una mantención con el celular en modo avión, cerrar y abrir la app, y volver a activar la señal. | Celular real (Chrome) | Manual | El formulario se guarda en el dispositivo, aparece «pendiente de enviar», se envía solo al volver la señal y no se duplica. | |
| CP06 | Seguridad | Cinco intentos de ingreso con clave incorrecta y luego uno con la clave correcta. | Django TestCase | Automática | La cuenta se bloquea 15 minutos aunque la clave final sea correcta; el evento queda en auditoría. | |
| CP07 | Validación | Enviar una mantención con horómetro final menor que el inicial. | Django TestCase · Postman | Automática / manual | El servidor responde 400 con el mensaje «debe ser mayor que»; no se guarda nada en ninguna base. | |
| CP08 | Seguridad | Un técnico externo intenta abrir y sincronizar un equipo que no tiene asignado. | Django TestCase · Postman | Automática / manual | Responde 403, no se guarda nada y queda un evento «acceso denegado» en la auditoría. | |
| CP09 | Validación | Subir un video de más de 30 segundos. | Django TestCase | Automática | El formulario se rechaza (400) y el video se elimina de Cloudinary. La duración que manda es la que informa Cloudinary, no la del celular. | |

## 9.3 Herramientas de prueba

| Herramienta | Tipo de prueba | Modo | Uso en el proyecto |
|---|---|---|---|
| Django `TestCase` / `unittest` | Unitarias, integración y seguridad | Automática | Reglas de negocio, permisos por perfil, auditoría, sincronización idempotente (`python manage.py test pruebas`). |
| pytest | Unitarias | Automática | Validadores, política de claves, repositorio de MongoDB en memoria y máquina de estados de tickets, sin base de datos (`pytest core/tests`). |
| Locust | Carga | Automática | CP03: técnicos simultáneos sobre el paquete de datos y la sincronización (`tests/locustfile.py`). |
| Postman | API | Manual | CP02, CP07, CP08: envíos de JSON y verificación de códigos 200/201/400/403 (`tests/COVEPA.postman_collection.json`). |
| Chrome en Android + DevTools / Lighthouse | PWA y usabilidad | Manual | CP04 y CP05; auditoría de PWA e instalación; modo avión. |

## 9.4 Resultados y evidencia

Ejecuta las pruebas, copia aquí el resultado y adjunta las capturas (Figura 12):

| ID | Fecha | Responsable | Resultado obtenido | Estado (Aprobado / Falló) | Evidencia |
|---|---|---|---|---|---|
| CP01 | | | | | |
| CP02 | | | | | |
| CP03 | | | | | |
| CP04 | | | | | |
| CP05 | | | | | |
| CP06 | | | | | |
| CP07 | | | | | |
| CP08 | | | | | |
| CP09 | | | | | |

Comandos:

```bash
python manage.py test pruebas        # CP01, CP02, CP06–CP09 y el resto (requiere Django instalado)
pytest core/tests                    # pruebas sin base de datos
locust -f tests/locustfile.py --host https://TU-PROYECTO.vercel.app --users 20 --spawn-rate 2 --run-time 3m --headless
```

## Lista de verificación manual en el celular (CP04 y CP05)

1. Abrir la URL en Chrome (Android) o Safari (iPhone) → «Instalar app» / «Agregar a inicio». Se abre sin barra del navegador y con el ícono COVEPA.
2. Ingresar como técnico con conexión. La pantalla de inicio muestra mantenciones por vencer y tickets asignados.
3. Activar modo avión. Aparece el aviso de «Sin conexión». Registrar una mantención con una foto y un video de menos de 30 s.
4. Probar un video de más de 30 s: la app lo rechaza al elegirlo.
5. Cerrar la app por completo, abrirla de nuevo sin señal: el formulario pendiente sigue visible.
6. Desactivar modo avión: el formulario se envía solo (o con «Enviar ahora») y desaparece de pendientes.
7. En el historial, abrir el registro: se ven las respuestas, las fotos y el video.
8. Revisar que los botones se puedan tocar con guantes, que el texto se lea al sol y que el modo oscuro funcione.

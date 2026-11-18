# Guía de contribución

## Roles del equipo
| Rol | Integrante |
|---|---|
| Product Owner | Raúl Rivera |
| Scrum Master | Angela Mancilla |
| Equipo de desarrollo | Luis Antivil, Héctor Beyer |

Todos los sprints son responsabilidad del equipo completo; cada integrante lidera las tareas de su rol.

## Flujo con Git
- `main`: siempre desplegable (Vercel despliega cada push). No se hace push directo.
- Ramas por historia: `hu-04-formulario-movil`, `fix-sync-duplicados`.
- Commits pequeños, en español, en imperativo: «Valida horómetro final mayor que inicial».
- Todo cambio entra por *pull request* con al menos una revisión de otro integrante.

## Lista de revisión de un PR
- [ ] Pasan `pytest core/tests` y `python manage.py test pruebas`.
- [ ] Las vistas obtienen equipos con `equipos_visibles` o `equipo_o_403`, nunca con `Equipo.objects` directo.
- [ ] Las acciones sensibles llaman a `auditoria.services.registrar`.
- [ ] No hay JavaScript en línea en las plantillas (la CSP lo bloquea); los datos entran al DOM con `textContent` o `COVEPA.el`.
- [ ] Los textos de pantalla están en español claro, con verbos de acción («Guardar mantención»).
- [ ] Si cambia un modelo: `makemigrations` y revisar el archivo generado.
- [ ] Ningún secreto en el repositorio (`.env` está en `.gitignore`).

## Estilo
`ruff check .` antes de subir. Nombres de dominio en español; código y comentarios en español.

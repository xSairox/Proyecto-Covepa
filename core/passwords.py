"""Política de contraseñas (sin dependencias de Django, para poder probarla aislada).

Informe, sección 8.2: mínimo 10 caracteres, con letras y números.
"""

from __future__ import annotations


def errores_politica(clave: str, largo_minimo: int = 10) -> list[str]:
    errores: list[str] = []
    if len(clave) < largo_minimo:
        errores.append(f"La contraseña debe tener al menos {largo_minimo} caracteres.")
    if not any(c.isalpha() for c in clave):
        errores.append("La contraseña debe incluir letras.")
    if not any(c.isdigit() for c in clave):
        errores.append("La contraseña debe incluir números.")
    return errores

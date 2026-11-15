"""Ciclo de vida de un ticket (informe, sección 5.3).

    Pendiente -> Aprobado -> En ejecución -> Realizado -> Cerrado
        |                                        |
        +-> Rechazado (con motivo)               +-> En ejecución (devuelto al técnico con observaciones)

Sin dependencias de Django, para poder probar la máquina de estados de forma aislada.
"""

PENDIENTE = "Pendiente"
APROBADO = "Aprobado"
EN_EJECUCION = "En ejecución"
REALIZADO = "Realizado"
CERRADO = "Cerrado"
RECHAZADO = "Rechazado"

ESTADOS = (PENDIENTE, APROBADO, EN_EJECUCION, REALIZADO, CERRADO, RECHAZADO)
ESTADOS_FINALES = (CERRADO, RECHAZADO)

TRANSICIONES = {
    PENDIENTE: {APROBADO, RECHAZADO},
    APROBADO: {EN_EJECUCION},
    EN_EJECUCION: {REALIZADO},
    REALIZADO: {CERRADO, EN_EJECUCION},  # EN_EJECUCION = devuelto con observaciones
    CERRADO: set(),
    RECHAZADO: set(),
}

# Estados que exigen una observación o un motivo
EXIGEN_MOTIVO = {RECHAZADO}


class TransicionInvalida(Exception):
    pass


def validar_transicion(actual: str, nuevo: str) -> None:
    if actual not in TRANSICIONES:
        raise TransicionInvalida(f"Estado desconocido: {actual}.")
    if nuevo not in TRANSICIONES[actual]:
        raise TransicionInvalida(f"No se puede pasar de '{actual}' a '{nuevo}'.")


def es_devolucion(actual: str, nuevo: str) -> bool:
    return actual == REALIZADO and nuevo == EN_EJECUCION

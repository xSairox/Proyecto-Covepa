"""Revisión estática de los archivos JS (sin navegador).

Error que detecta: pasar un ARREGLO a append()/prepend()/before()/after() nativos del DOM.
Esos métodos no aceptan arreglos: los convierten a texto y en pantalla aparece
"[object HTMLOptionElement],[object HTMLOptionElement]". Solo el helper el() aplana arreglos.
Correcto: nodo.append(...lista.map(...))  /  nodo.replaceChildren(...lista)  /  el('x', {}, lista.map(...)).
"""

import re
import unittest
from pathlib import Path

JS = Path(__file__).resolve().parents[2] / "static" / "js"
METODOS = re.compile(r"\.(append|prepend|before|after|replaceChildren)\(")
ARREGLO = re.compile(r"^(?!\.\.\.)[\w$.\[\]]+\.(map|filter|flat|flatMap|slice|concat)\(")


def _argumentos(codigo: str, abre: int) -> list[str]:
    """Devuelve los argumentos de primer nivel de la llamada cuyo '(' está en la posición abre."""
    args, actual, nivel, i = [], [], 0, abre
    while i < len(codigo):
        c = codigo[i]
        if c in "'\"`":  # saltar cadenas y plantillas
            fin = i + 1
            while fin < len(codigo) and codigo[fin] != c:
                fin += 2 if codigo[fin] == "\\" else 1
            actual.append(codigo[i : fin + 1])
            i = fin + 1
            continue
        if c in "([{":
            nivel += 1
            if nivel > 1:
                actual.append(c)
        elif c in ")]}":
            nivel -= 1
            if nivel == 0:
                args.append("".join(actual).strip())
                return args
            actual.append(c)
        elif c == "," and nivel == 1:
            args.append("".join(actual).strip())
            actual = []
        else:
            actual.append(c)
        i += 1
    return args


def arreglos_sin_esparcir(codigo: str) -> list[tuple[int, str]]:
    problemas = []
    for m in METODOS.finditer(codigo):
        for arg in _argumentos(codigo, m.end() - 1):
            if ARREGLO.match(arg):  # no empieza con "..." y es una expresión que devuelve arreglo
                problemas.append((codigo.count("\n", 0, m.start()) + 1, arg[:60]))
    return problemas


class ArreglosEnAppendTest(unittest.TestCase):
    def test_detecta_el_error(self):
        malo = "sel.append(el('option'), lista.map((e) => el('option')));"
        self.assertEqual(len(arreglos_sin_esparcir(malo)), 1)

    def test_acepta_la_forma_correcta(self):
        bueno = "sel.append(el('option'), ...lista.map((e) => el('option')));"
        self.assertEqual(arreglos_sin_esparcir(bueno), [])

    def test_archivos_js_sin_arreglos_en_append(self):
        for archivo in sorted(JS.glob("*.js")):
            with self.subTest(archivo=archivo.name):
                self.assertEqual(arreglos_sin_esparcir(archivo.read_text(encoding="utf-8")), [])


if __name__ == "__main__":
    unittest.main()

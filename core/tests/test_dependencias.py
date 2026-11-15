"""Vercel instala desde pyproject.toml (tiene prioridad sobre requirements.txt).

Si las dos listas se desalinean, el despliegue puede quedar sin Django u otra librería.
"""

import re
import tomllib
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _nombre(requisito: str) -> str:
    requisito = requisito.split("#")[0].strip()
    return re.split(r"[\[<>=!~ ;]", requisito, maxsplit=1)[0].lower().replace("_", "-")


def _normalizar(requisito: str) -> str:
    return re.sub(r"\s+", "", requisito.split("#")[0]).lower()


class DependenciasAlineadasTest(unittest.TestCase):
    def setUp(self):
        proyecto = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
        self.en_pyproject = {_normalizar(d) for d in proyecto["project"]["dependencies"]}
        lineas = (RAIZ / "requirements.txt").read_text(encoding="utf-8").splitlines()
        self.en_requirements = {_normalizar(x) for x in lineas if x.strip() and not x.startswith(("#", "-"))}

    def test_pyproject_declara_dependencias(self):
        self.assertTrue(self.en_pyproject, "pyproject.toml no declara dependencias.")

    def test_mismas_dependencias_en_ambos_archivos(self):
        self.assertEqual(self.en_pyproject, self.en_requirements)

    def test_django_esta_declarado(self):
        self.assertIn("django", {_nombre(d) for d in self.en_pyproject})


if __name__ == "__main__":
    unittest.main()

"""Configuration Sphinx : référence du code générée depuis les docstrings.

Construction (après mkdocs build, qui vide site/) :
    sphinx-build -W -b html sphinx site/code
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

project = "Turnover API"
author = "Projet turnover_model"
language = "fr"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",  # docstrings au format Google (Args, Returns, Raises)
    "sphinx.ext.viewcode",  # lien vers le code source
]

autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "show-inheritance": True,
}
autodoc_typehints = "description"
napoleon_google_docstring = True
napoleon_numpy_docstring = False

html_theme = "furo"
html_title = "Turnover API — référence du code"
exclude_patterns = ["_build"]

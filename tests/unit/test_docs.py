"""La documentation reste synchronisée avec le code."""

import re
from pathlib import Path

import yaml

from scripts.export_openapi import CHEMIN_OPENAPI, generer_openapi

RACINE = Path(__file__).resolve().parents[2]


def test_openapi_a_jour():
    """Après une modification de l'API : python -m scripts.export_openapi"""
    assert CHEMIN_OPENAPI.read_text(encoding="utf-8") == generer_openapi()


def test_chaque_page_markdown_est_dans_le_menu():
    """Une page absente du menu MkDocs est introuvable pour le lecteur."""

    class Chargeur(yaml.SafeLoader):
        pass

    # mkdocs.yml contient une balise Python (!!python/name) : on l'ignore ici.
    Chargeur.add_multi_constructor("tag:yaml.org,2002:python/", lambda *_: None)
    config = yaml.load((RACINE / "mkdocs.yml").read_text(encoding="utf-8"), Loader=Chargeur)
    dans_le_menu = set(re.findall(r"[\w/-]+\.md", str(config["nav"])))

    pages = {p.relative_to(RACINE / "docs").as_posix() for p in (RACINE / "docs").rglob("*.md")}

    assert pages == dans_le_menu


def test_chaque_module_est_dans_la_reference_sphinx():
    modules = {
        ".".join(p.relative_to(RACINE).with_suffix("").parts)
        for dossier in ("app", "src", "scripts")
        for p in (RACINE / dossier).rglob("*.py")
        if p.name != "__init__.py"
    }
    documentes = set()
    for rst in (RACINE / "sphinx").glob("*.rst"):
        documentes |= set(re.findall(r"automodule:: ([\w.]+)", rst.read_text(encoding="utf-8")))

    assert modules == documentes

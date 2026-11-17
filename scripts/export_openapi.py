"""Exporte le schéma OpenAPI de l'API dans docs/api/openapi.json.

Usage : python -m scripts.export_openapi

Ce fichier est affiché par Swagger UI dans la documentation MkDocs.
Un test unitaire vérifie qu'il est à jour : à relancer après toute
modification de l'API (routes, schémas, descriptions).
"""

import json
from pathlib import Path

from app.main import app

CHEMIN_OPENAPI = Path(__file__).resolve().parents[1] / "docs" / "api" / "openapi.json"


def generer_openapi() -> str:
    """Renvoie le schéma OpenAPI de l'API, sous forme de JSON indenté."""
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    CHEMIN_OPENAPI.parent.mkdir(parents=True, exist_ok=True)
    CHEMIN_OPENAPI.write_text(generer_openapi(), encoding="utf-8")
    print(f"Schéma OpenAPI exporté : {CHEMIN_OPENAPI}")


if __name__ == "__main__":
    main()

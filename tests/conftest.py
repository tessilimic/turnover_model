"""Configuration commune des tests.

Catégories (marqueur ajouté automatiquement selon le dossier) :
  * tests/unit/        -> unit        : une fonction isolée, sans base ni vrai modèle ;
  * tests/integration/ -> integration : base de données réelle, modèle exporté ;
  * tests/functional/  -> functional  : l'API appelée en HTTP, de bout en bout.
Exemple : pytest -m unit

Base de données : PostgreSQL si TEST_DATABASE_URL est défini (CI), sinon un
fichier SQLite temporaire. DATABASE_URL est écrasé AVANT tout import de
l'application : les tests ne touchent jamais la base de développement.
"""

import os
import tempfile
from pathlib import Path

import pytest

_DOSSIER_TMP = Path(tempfile.mkdtemp(prefix="turnover-tests-"))
os.environ["DATABASE_URL"] = (
    os.getenv("TEST_DATABASE_URL") or f"sqlite:///{(_DOSSIER_TMP / 'test.db').as_posix()}"
)

from src.db.init_db import charger_csv_en_base  # noqa: E402
from src.db.session import creer_schema, get_engine, supprimer_schema  # noqa: E402

CATEGORIES = ("unit", "integration", "functional")


def pytest_collection_modifyitems(config, items):
    for item in items:
        categorie = item.path.parent.name
        if categorie not in CATEGORIES:
            raise pytest.UsageError(
                f"{item.nodeid} : chaque test doit être rangé dans tests/{{{','.join(CATEGORIES)}}}/"
            )
        item.add_marker(categorie)


@pytest.fixture(scope="session")
def engine():
    """Base vierge, schéma créé, jeu initial chargé : une fois pour toute la session."""
    engine = get_engine()
    supprimer_schema(engine)
    creer_schema(engine)
    charger_csv_en_base(engine)
    yield engine
    engine.dispose()

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
URL_TEST = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{(_DOSSIER_TMP / 'test.db').as_posix()}"
# Toutes les adresses pointent vers la base de test, même si un .env local en définit
# d'autres (le .env est chargé à l'import de src.db.session, sans écraser ces valeurs).
for variable in ("DATABASE_URL", "ADMIN_DATABASE_URL", "ML_DATABASE_URL"):
    os.environ[variable] = URL_TEST
os.environ["JWT_SECRET"] = "secret-de-test-uniquement-0123456789abcdef"
for variable in ("ADMIN_USERNAME", "ADMIN_PASSWORD"):
    os.environ.pop(variable, None)

from app.auth import creer_jeton  # noqa: E402
from app.utilisateurs import creer_utilisateur  # noqa: E402
from src.db.init_db import charger_csv_en_base  # noqa: E402
from src.db.session import creer_schema, get_engine, supprimer_schema  # noqa: E402

CATEGORIES = ("unit", "integration", "functional")

#: Comptes créés dans la base de test (identifiant -> rôle) et leur mot de passe commun.
COMPTES = {"rh.test": "rh", "auditeur.test": "auditeur", "admin.test": "admin"}
MOT_DE_PASSE_TEST = "Motdepasse-de-test-42"


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
    """Base vierge, schéma créé, jeu initial et comptes de test chargés (une fois par session)."""
    from sqlalchemy.orm import Session

    engine = get_engine()
    supprimer_schema(engine)
    creer_schema(engine)
    charger_csv_en_base(engine)
    with Session(engine) as session:
        for identifiant, role in COMPTES.items():
            creer_utilisateur(session, identifiant, MOT_DE_PASSE_TEST, role)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def auth(engine) -> dict[str, dict[str, str]]:
    """En-têtes d'authentification par rôle : ``auth["rh"]``, ``auth["auditeur"]``, ``auth["admin"]``."""
    return {
        role: {"Authorization": f"Bearer {creer_jeton(identifiant, role)}"}
        for identifiant, role in COMPTES.items()
    }


@pytest.fixture(scope="session")
def mot_de_passe_test() -> str:
    """Mot de passe des comptes de test (conforme à la politique)."""
    return MOT_DE_PASSE_TEST

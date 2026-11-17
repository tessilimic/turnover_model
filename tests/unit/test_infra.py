"""Configuration de la base et chargement du modèle, sans base ni vrai modèle."""

from types import SimpleNamespace

import joblib
import pytest
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline

import src.db.session as db_session
from app.model import get_modele


# ---------- URL de la base ----------

def test_url_par_defaut_vise_le_postgresql_de_docker_compose(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    url = db_session.get_database_url()

    assert url.startswith("postgresql+psycopg://")
    assert "localhost:5433" in url


def test_url_lue_dans_la_variable_d_environnement(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///autre.db")

    assert db_session.get_database_url() == "sqlite:///autre.db"


# ---------- Création / suppression du schéma selon la base ----------

@pytest.fixture
def fichiers_sql_executes(monkeypatch):
    executes = []
    monkeypatch.setattr(db_session, "_executer_fichier_sql", lambda _, nom: executes.append(nom))
    return executes


def faux_engine(dialecte: str):
    return SimpleNamespace(dialect=SimpleNamespace(name=dialecte))


def test_postgresql_utilise_les_fichiers_sql(fichiers_sql_executes):
    db_session.creer_schema(faux_engine("postgresql"))
    db_session.supprimer_schema(faux_engine("postgresql"))

    assert fichiers_sql_executes == ["01_schema.sql", "00_reset.sql"]


def test_sqlite_utilise_l_orm(monkeypatch, fichiers_sql_executes):
    appels = []
    monkeypatch.setattr(db_session.Base.metadata, "create_all", lambda e: appels.append("create"))
    monkeypatch.setattr(db_session.Base.metadata, "drop_all", lambda e: appels.append("drop"))

    db_session.creer_schema(faux_engine("sqlite"))
    db_session.supprimer_schema(faux_engine("sqlite"))

    assert appels == ["create", "drop"]
    assert fichiers_sql_executes == []


def test_fichiers_sql_presents():
    for nom in ("00_reset.sql", "01_schema.sql"):
        assert (db_session.DOSSIER_SQL / nom).is_file()


# ---------- Chargement du modèle ----------

@pytest.fixture
def faux_artefact(tmp_path, monkeypatch):
    """Petit artefact factice, désigné par MODEL_PATH ; cache vidé avant et après."""
    chemin = tmp_path / "pipeline.joblib"
    pipeline = Pipeline([("clf", RandomForestClassifier(n_estimators=2, n_jobs=-1))])
    joblib.dump({"pipeline": pipeline, "seuil": 0.5}, chemin)
    monkeypatch.setenv("MODEL_PATH", str(chemin))
    get_modele.cache_clear()
    yield chemin
    get_modele.cache_clear()


def test_modele_charge_depuis_model_path(faux_artefact):
    assert get_modele()["seuil"] == 0.5


def test_modele_charge_une_seule_fois(faux_artefact):
    assert get_modele() is get_modele()


def test_prediction_sur_un_seul_coeur(faux_artefact):
    assert get_modele()["pipeline"].named_steps["clf"].n_jobs == 1


def test_fichier_absent_leve_une_erreur(tmp_path, monkeypatch):
    monkeypatch.setenv("MODEL_PATH", str(tmp_path / "absent.joblib"))
    get_modele.cache_clear()
    try:
        with pytest.raises(FileNotFoundError):
            get_modele()
    finally:
        get_modele.cache_clear()

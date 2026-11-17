"""Logique de /predict, isolée : faux modèle et fausse session (aucune base, aucun .joblib).

Pas de "with TestClient(...)" : le démarrage de l'API (chargement du vrai
modèle, création des tables) n'est pas exécuté.
"""

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.model import get_modele
from app.schemas import EXEMPLE_EMPLOYE
from src.db.models import Employe
from src.db.session import get_session
from src.features import COLONNES_ENTREE


class FauxPipeline:
    """Renvoie toujours la même probabilité et garde les entrées reçues."""

    def __init__(self, proba: float):
        self.proba = proba
        self.recu: pd.DataFrame | None = None

    def predict_proba(self, X: pd.DataFrame):
        self.recu = X
        return np.array([[1 - self.proba, self.proba]])  # même format que scikit-learn


class FausseSession:
    """Enregistre les appels au lieu d'écrire en base."""

    def __init__(self):
        self.ajouts: list = []
        self.commits = 0

    def add(self, objet):
        self.ajouts.append(objet)

    def commit(self):
        self.commits += 1
        for employe in self.ajouts:
            for prediction in employe.predictions:
                prediction.id = 42  # identifiant attribué par la base


@pytest.fixture
def predire():
    """Appelle /predict avec un faux modèle de probabilité donnée."""
    session = FausseSession()
    pipelines = []

    def _predire(proba: float, seuil: float = 0.41, employe: dict = EXEMPLE_EMPLOYE):
        pipeline = FauxPipeline(proba)
        pipelines.append(pipeline)
        app.dependency_overrides[get_modele] = lambda: {
            "pipeline": pipeline, "seuil": seuil, "colonnes_entree": COLONNES_ENTREE,
        }
        app.dependency_overrides[get_session] = lambda: session
        return TestClient(app).post("/predict", json=employe)

    _predire.session = session
    _predire.pipelines = pipelines
    yield _predire
    app.dependency_overrides.clear()


# ---------- Décision selon le seuil ----------

@pytest.mark.parametrize(
    ("proba", "seuil", "attendu"),
    [
        (0.90, 0.41, True),
        (0.41, 0.41, True),    # égalité : départ prédit (>=)
        (0.4099, 0.41, False),
        (0.10, 0.41, False),
        (0.60, 0.70, False),   # le seuil vient du modèle, pas d'une constante
    ],
)
def test_decision_depend_du_seuil(predire, proba, seuil, attendu):
    body = predire(proba, seuil).json()

    assert body["depart_predit"] is attendu
    assert body["seuil"] == seuil


def test_probabilite_arrondie_a_4_decimales(predire):
    assert predire(0.123456789).json()["probabilite_depart"] == 0.1235


def test_renvoie_l_identifiant_attribue_par_la_base(predire):
    assert predire(0.5).json()["id_prediction"] == 42


# ---------- Ce qui est transmis au modèle ----------

def test_modele_recoit_une_ligne_dans_l_ordre_attendu(predire):
    # Champs envoyés dans le désordre : l'API doit les remettre dans l'ordre du modèle.
    desordre = dict(reversed(list(EXEMPLE_EMPLOYE.items())))

    predire(0.5, employe=desordre)

    recu = predire.pipelines[-1].recu
    assert list(recu.columns) == COLONNES_ENTREE
    assert recu.iloc[0].to_dict() == EXEMPLE_EMPLOYE


# ---------- Ce qui est enregistré ----------

def test_enregistre_entrees_et_sortie_puis_valide(predire):
    predire(0.7)

    session = predire.session
    assert session.commits == 1
    (employe,) = session.ajouts
    assert isinstance(employe, Employe)
    assert employe.id_employee is None
    assert {col: getattr(employe, col) for col in COLONNES_ENTREE} == EXEMPLE_EMPLOYE

    (prediction,) = employe.predictions
    assert prediction.origine == "prediction"
    assert prediction.probabilite == 0.7       # non arrondie en base
    assert prediction.seuil == 0.41
    assert prediction.depart is True


def test_entree_invalide_ni_predite_ni_enregistree(predire):
    response = predire(0.5, employe=EXEMPLE_EMPLOYE | {"genre": "X"})

    assert response.status_code == 422
    assert predire.pipelines[-1].recu is None
    assert predire.session.ajouts == []
    assert predire.session.commits == 0

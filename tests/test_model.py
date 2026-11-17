from pathlib import Path

import joblib
import pandas as pd
import pytest
import sklearn

from src.db.init_db import lire_csv
from src.features import CIBLE, COLONNES_ENTREE
from src.train import charger_donnees, separer_x_y

CHEMIN_MODELE = Path(__file__).resolve().parents[1] / "model" / "pipeline.joblib"


@pytest.fixture(scope="module")
def artefact() -> dict:
    return joblib.load(CHEMIN_MODELE)


@pytest.fixture(scope="module")
def donnees(engine):
    return separer_x_y(charger_donnees(engine))


def test_charger_donnees(donnees):
    X, y = donnees

    assert X.shape == (1470, 24)
    assert list(X.columns) == COLONNES_ENTREE
    assert not X.isna().any().any()
    assert set(y.unique()) == {0, 1}


def test_donnees_en_base_identiques_aux_csv(donnees):
    """Entraîner depuis la base ou depuis les CSV donne exactement les mêmes données."""
    X, y = donnees
    csv = lire_csv()

    pd.testing.assert_frame_equal(
        X.reset_index(drop=True), csv[COLONNES_ENTREE].reset_index(drop=True), check_dtype=False
    )
    assert y.tolist() == csv[CIBLE].eq("Oui").astype(int).tolist()


def test_predictions_api_exclues_de_l_entrainement(engine, donnees):
    from sqlalchemy.orm import Session

    from app.schemas import EXEMPLE_EMPLOYE
    from src.db.models import Employe, Prediction

    with Session(engine) as session:
        session.add(Employe(**EXEMPLE_EMPLOYE, predictions=[
            Prediction(origine="prediction", depart=True, probabilite=0.9, seuil=0.41)
        ]))
        session.commit()

    X, _ = separer_x_y(charger_donnees(engine))

    assert len(X) == len(donnees[0]) == 1470


def test_artefact_contient_pipeline_et_seuil(artefact):
    assert {"pipeline", "seuil", "colonnes_entree", "versions"} <= artefact.keys()
    assert artefact["seuil"] == 0.41
    assert artefact["colonnes_entree"] == COLONNES_ENTREE


def test_version_scikit_learn_identique(artefact):
    # Un modèle exporté avec une autre version peut se recharger de travers.
    assert artefact["versions"]["scikit-learn"] == sklearn.__version__


def test_pipeline_predit_des_probabilites(artefact, donnees):
    X, _ = donnees

    proba = artefact["pipeline"].predict_proba(X.head(20))[:, 1]

    assert proba.shape == (20,)
    assert ((proba >= 0) & (proba <= 1)).all()


def test_entrainement_reproduit_le_notebook(donnees):
    from sklearn.model_selection import train_test_split

    from src.train import RANDOM_STATE, SEUIL, construire_pipeline, evaluer

    X, y = donnees
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=RANDOM_STATE
    )

    metriques = evaluer(construire_pipeline().fit(X_train, y_train), X_test, y_test, SEUIL)

    # Valeurs du notebook (cellule 20)
    assert metriques["roc_auc"] == pytest.approx(0.769, abs=0.001)
    assert metriques["recall"] == pytest.approx(0.81, abs=0.01)


def test_performance_minimale(artefact, donnees):
    # Garde-fou contre un modèle cassé (entraîné sur toutes les données).
    from sklearn.metrics import roc_auc_score

    X, y = donnees
    proba = artefact["pipeline"].predict_proba(X)[:, 1]

    assert roc_auc_score(y, proba) > 0.75

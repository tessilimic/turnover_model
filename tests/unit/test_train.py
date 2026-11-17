"""Fonctions de src/train.py, sur des données fabriquées (sans base)."""

import numpy as np
import pandas as pd
import pytest
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import FunctionTransformer

from app.schemas import EXEMPLE_EMPLOYE
from src.features import COLONNES_ENTREE, ajouter_features
from src.train import HYPERPARAMETRES, RANDOM_STATE, construire_pipeline, evaluer, separer_x_y


# ---------- separer_x_y ----------

def test_separer_x_y_garde_les_colonnes_d_entree_dans_l_ordre():
    df = pd.DataFrame([EXEMPLE_EMPLOYE | {"depart": True, "colonne_en_trop": 1}])

    X, y = separer_x_y(df)

    assert list(X.columns) == COLONNES_ENTREE
    assert "depart" not in X and "colonne_en_trop" not in X


@pytest.mark.parametrize("depart", [[True, False], [1, 0]])  # PostgreSQL : bool, SQLite : 0/1
def test_separer_x_y_convertit_la_cible_en_0_1(depart):
    df = pd.DataFrame([EXEMPLE_EMPLOYE, EXEMPLE_EMPLOYE]).assign(depart=depart)

    _, y = separer_x_y(df)

    assert y.tolist() == [1, 0]


# ---------- construire_pipeline ----------

def test_pipeline_enchaine_features_encodage_et_foret():
    pipeline = construire_pipeline()

    assert list(pipeline.named_steps) == ["features", "prep", "clf"]
    assert isinstance(pipeline.named_steps["features"], FunctionTransformer)
    assert pipeline.named_steps["features"].func is ajouter_features
    assert isinstance(pipeline.named_steps["prep"], ColumnTransformer)
    assert isinstance(pipeline.named_steps["clf"], RandomForestClassifier)


def test_pipeline_utilise_les_hyperparametres_du_notebook():
    params = construire_pipeline().named_steps["clf"].get_params()

    assert {k: params[k] for k in HYPERPARAMETRES} == HYPERPARAMETRES
    assert params["random_state"] == RANDOM_STATE


def test_pipeline_neuf_a_chaque_appel():
    assert construire_pipeline() is not construire_pipeline()


# ---------- evaluer ----------

class FauxModele:
    def __init__(self, proba):
        self.proba = np.asarray(proba)

    def predict_proba(self, X):
        return np.column_stack([1 - self.proba, self.proba])


def test_evaluer_applique_le_seuil():
    y = pd.Series([1, 1, 0, 0])
    modele = FauxModele([0.9, 0.5, 0.45, 0.1])

    # Seuil 0.41 : prédit [1, 1, 1, 0] -> 2 vrais positifs, 1 fausse alerte
    m = evaluer(modele, None, y, seuil=0.41)

    assert m["recall"] == 1.0
    assert m["precision"] == pytest.approx(2 / 3)
    assert m["roc_auc"] == 1.0  # le classement des probabilités est parfait


def test_evaluer_seuil_plus_haut_moins_d_alertes():
    y = pd.Series([1, 1, 0, 0])
    modele = FauxModele([0.9, 0.5, 0.45, 0.1])

    m = evaluer(modele, None, y, seuil=0.6)  # prédit [1, 0, 0, 0]

    assert m["recall"] == 0.5
    assert m["precision"] == 1.0


def test_evaluer_sans_aucune_alerte_ne_plante_pas():
    m = evaluer(FauxModele([0.1, 0.2, 0.3]), None, pd.Series([1, 0, 0]), seuil=0.9)

    assert m["precision"] == 0.0
    assert m["recall"] == 0.0

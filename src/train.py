"""Entraîne le modèle de turnover et l'exporte dans model/.

Usage : python -m src.train
(base remplie au préalable par : python -m src.db.init_db)

Reprend le modèle final du notebook (hyperparamètres et seuil retenus) :
1. évaluation sur un jeu de test (80/20 stratifié, comme le notebook) ;
2. réentraînement sur toutes les données, puis export.
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, OrdinalEncoder

from sqlalchemy import Engine, select

from src.db.models import Employe, Prediction
from src.db.session import creer_engine, get_database_url
from src.features import (
    BINAIRES,
    COLONNES_ENTREE,
    NOMINALES,
    NUMERIQUES,
    ORDINALES,
    ORDRE_DEPLACEMENT,
    ajouter_features,
)

RACINE = Path(__file__).resolve().parents[1]
DOSSIER_MODELE = RACINE / "model"

RANDOM_STATE = 42
SEUIL = 0.41  # F2 max en validation croisée (notebook)
HYPERPARAMETRES = {
    "n_estimators": 300,
    "max_depth": 4,
    "min_samples_leaf": 20,
    "max_features": "sqrt",
    "class_weight": "balanced_subsample",
}


def charger_donnees(engine: Engine) -> pd.DataFrame:
    """Lit le jeu d'entraînement en base : employés avec un départ observé.

    Les prédictions faites par l'API ne servent jamais à l'entraînement.
    Tri par ``id_employee`` : même ordre que les CSV, donc même découpage train/test.

    Args:
        engine: Connexion SQLAlchemy (PostgreSQL ou SQLite).

    Returns:
        Une ligne par employé : les colonnes de :data:`~src.features.COLONNES_ENTREE`
        et ``depart`` (départ observé).
    """
    requete = (
        select(*(getattr(Employe, col) for col in COLONNES_ENTREE), Prediction.depart)
        .join(Prediction, Prediction.employe_id == Employe.id)
        .where(Prediction.origine == "observation")
        .order_by(Employe.id_employee)
    )
    with engine.connect() as conn:
        return pd.read_sql_query(requete, conn)


def separer_x_y(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Sépare les entrées du modèle et la cible.

    Args:
        df: Résultat de :func:`charger_donnees`.

    Returns:
        ``(X, y)`` : les colonnes d'entrée dans l'ordre attendu, et la cible
        en 0/1 (``True`` sous PostgreSQL et ``1`` sous SQLite donnent tous deux 1).
    """
    X = df[COLONNES_ENTREE]
    y = df["depart"].astype(int)
    return X, y


def construire_pipeline() -> Pipeline:
    """Construit le pipeline complet, non entraîné.

    Étapes :

    1. ``features`` : :func:`~src.features.ajouter_features` ;
    2. ``prep`` : one-hot (nominales, binaires), ordinal (déplacements),
       numériques inchangées (pas de mise à l'échelle pour des arbres) ;
    3. ``clf`` : forêt aléatoire (:data:`HYPERPARAMETRES`).

    Returns:
        Un pipeline scikit-learn neuf à chaque appel.
    """
    preprocesseur = ColumnTransformer([
        ("nom", OneHotEncoder(handle_unknown="ignore"), NOMINALES),
        ("bin", OneHotEncoder(drop="if_binary"), BINAIRES),
        ("ord", OrdinalEncoder(categories=[ORDRE_DEPLACEMENT]), ORDINALES),
        ("num", "passthrough", NUMERIQUES),  # arbres : pas de mise à l'échelle
    ])
    return Pipeline([
        ("features", FunctionTransformer(ajouter_features)),
        ("prep", preprocesseur),
        ("clf", RandomForestClassifier(**HYPERPARAMETRES, random_state=RANDOM_STATE, n_jobs=-1)),
    ])


def evaluer(pipeline: Pipeline, X: pd.DataFrame, y: pd.Series, seuil: float) -> dict[str, float]:
    """Calcule les métriques d'évaluation au seuil donné.

    Args:
        pipeline: Modèle entraîné (doit fournir ``predict_proba``).
        X: Entrées.
        y: Départs réels (0/1).
        seuil: Probabilité à partir de laquelle un départ est prédit.

    Returns:
        ``roc_auc`` et ``pr_auc`` (indépendants du seuil), puis ``recall``,
        ``precision``, ``f1`` et ``balanced_accuracy`` au seuil.
    """
    proba = pipeline.predict_proba(X)[:, 1]
    pred = (proba >= seuil).astype(int)
    return {
        "roc_auc": roc_auc_score(y, proba),
        "pr_auc": average_precision_score(y, proba),
        "recall": recall_score(y, pred, zero_division=0),
        "precision": precision_score(y, pred, zero_division=0),
        "f1": f1_score(y, pred, zero_division=0),
        "balanced_accuracy": balanced_accuracy_score(y, pred),
    }


def main() -> None:
    engine = creer_engine(get_database_url("ML_DATABASE_URL"))  # lecture seule
    print(f"Données lues dans : {engine.url.render_as_string(hide_password=True)}")
    X, y = separer_x_y(charger_donnees(engine))
    if X.empty:
        raise SystemExit("Aucune donnée en base : lancer d'abord python -m src.db.init_db")

    # 1. Évaluation (même découpage que le notebook)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=RANDOM_STATE
    )
    pipeline = construire_pipeline().fit(X_train, y_train)
    metriques = {k: round(float(v), 3) for k, v in evaluer(pipeline, X_test, y_test, SEUIL).items()}
    print(f"Métriques sur le test (seuil {SEUIL}) :")
    for nom, valeur in metriques.items():
        print(f"  {nom:<18} {valeur:.3f}")

    # 2. Modèle final : réentraîné sur toutes les données
    pipeline = construire_pipeline().fit(X, y)

    metadonnees = {
        "seuil": SEUIL,
        "colonnes_entree": COLONNES_ENTREE,
        "hyperparametres": HYPERPARAMETRES,
        "metriques_test": metriques,
        "source_donnees": engine.dialect.name,
        "n_lignes_entrainement": int(len(X)),
        "taux_depart": round(float(np.mean(y)), 3),
        "versions": {"scikit-learn": sklearn.__version__, "pandas": pd.__version__,
                     "numpy": np.__version__},
    }

    DOSSIER_MODELE.mkdir(exist_ok=True)
    chemin = DOSSIER_MODELE / "pipeline.joblib"
    joblib.dump({"pipeline": pipeline, **metadonnees}, chemin, compress=3)
    (DOSSIER_MODELE / "metadata.json").write_text(
        json.dumps(metadonnees, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nModèle exporté : {chemin.relative_to(RACINE)} ({chemin.stat().st_size / 1024:.0f} Ko)")


if __name__ == "__main__":
    main()

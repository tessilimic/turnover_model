"""Chargement du modèle exporté par src/train.py."""

import os
from functools import lru_cache
from pathlib import Path

import joblib

CHEMIN_PAR_DEFAUT = Path(__file__).resolve().parents[1] / "model" / "pipeline.joblib"


@lru_cache
def get_modele() -> dict:
    """Charge le modèle exporté, une seule fois (résultat mis en cache).

    Le chemin est lu dans la variable d'environnement ``MODEL_PATH``
    (par défaut ``model/pipeline.joblib``).

    Returns:
        Le dictionnaire exporté par :mod:`src.train` : ``pipeline``, ``seuil``,
        ``colonnes_entree``, ``metriques_test``, ``versions``...

    Raises:
        FileNotFoundError: Si le fichier du modèle est absent.
    """
    chemin = Path(os.getenv("MODEL_PATH", CHEMIN_PAR_DEFAUT))
    modele = joblib.load(chemin)
    # Une prédiction = quelques lignes : le parallélisme coûte plus qu'il ne rapporte.
    modele["pipeline"].named_steps["clf"].set_params(n_jobs=1)
    return modele

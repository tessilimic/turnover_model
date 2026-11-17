"""Chargement du modèle exporté par src/train.py."""

import os
from functools import lru_cache
from pathlib import Path

import joblib

CHEMIN_PAR_DEFAUT = Path(__file__).resolve().parents[1] / "model" / "pipeline.joblib"


@lru_cache
def get_modele() -> dict:
    """Charge le modèle une seule fois (pipeline, seuil, colonnes d'entrée...)."""
    chemin = Path(os.getenv("MODEL_PATH", CHEMIN_PAR_DEFAUT))
    modele = joblib.load(chemin)
    # Une prédiction = quelques lignes : le parallélisme coûte plus qu'il ne rapporte.
    modele["pipeline"].named_steps["clf"].set_params(n_jobs=1)
    return modele

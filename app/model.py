"""Chargement du modèle exporté par src/train.py."""

import hashlib
import logging
import os
from functools import lru_cache
from pathlib import Path

import joblib

CHEMIN_PAR_DEFAUT = Path(__file__).resolve().parents[1] / "model" / "pipeline.joblib"

journal = logging.getLogger("turnover.modele")


@lru_cache
def get_modele() -> dict:
    """Charge le modèle exporté, une seule fois (résultat mis en cache).

    Le chemin est lu dans la variable d'environnement ``MODEL_PATH``
    (par défaut ``model/pipeline.joblib``).

    Returns:
        Le dictionnaire exporté par :mod:`src.train` : ``pipeline``, ``seuil``,
        ``colonnes_entree``, ``metriques_test``, ``versions``..., complété par
        ``empreinte`` (début du SHA-256 du fichier), qui identifie le modèle
        utilisé dans les logs et le journal des interactions.

    Raises:
        FileNotFoundError: Si le fichier du modèle est absent.
    """
    chemin = Path(os.getenv("MODEL_PATH", CHEMIN_PAR_DEFAUT))
    modele = joblib.load(chemin)
    # Une prédiction = quelques lignes : le parallélisme coûte plus qu'il ne rapporte.
    modele["pipeline"].named_steps["clf"].set_params(n_jobs=1)
    modele["empreinte"] = hashlib.sha256(chemin.read_bytes()).hexdigest()[:12]
    journal.info(
        "modèle chargé",
        extra={"evenement": "modele.chargement", "chemin": str(chemin),
               "empreinte": modele["empreinte"], "seuil": modele.get("seuil")},
    )
    return modele

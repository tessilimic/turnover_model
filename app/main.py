"""Application FastAPI : routes de l'API de prédiction du turnover.

La documentation interactive (Swagger UI) est générée à partir de ce fichier
et de :mod:`app.schemas` ; elle est servie sur ``/docs``.
"""

from contextlib import asynccontextmanager
from typing import Annotated

import pandas as pd
from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.model import get_modele
from app.schemas import EmployeInput, PredictionOutput
from src.db.models import Employe, Prediction
from src.db.session import creer_schema, get_engine, get_session

DESCRIPTION = """
Estime le **risque de départ** d'un employé à partir de son profil RH
(SIRH, sondage interne, évaluations).

* Modèle : Random Forest (scikit-learn), seuil de décision **0,41**,
  choisi pour détecter un maximum de départs (F2).
* Chaque prédiction est **enregistrée** en base (entrées et résultat).
* Documentation complète : guide utilisateur, fiche du modèle, architecture
  et maintenance dans le dossier `docs/` du dépôt (site MkDocs).
"""

TAGS = [
    {"name": "prédiction", "description": "Estimer le risque de départ d'un employé."},
    {"name": "monitoring", "description": "Vérifier que le service est en ligne."},
]

EXEMPLE_422 = {
    "detail": [{
        "type": "literal_error",
        "loc": ["body", "poste"],
        "msg": "Input should be 'Assistant de Direction', 'Cadre Commercial', ...",
        "input": "Astronaute",
    }]
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Au démarrage : charge le modèle et crée les tables si besoin.

    Une erreur (modèle absent, base injoignable) est ainsi visible tout de
    suite, et la première requête n'attend pas le chargement du modèle.
    """
    get_modele()
    creer_schema(get_engine())  # idempotent
    yield


app = FastAPI(
    title="Turnover API",
    summary="Prédiction du risque de départ des employés.",
    description=DESCRIPTION,
    version="0.3.0",
    openapi_tags=TAGS,
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Page d'accueil du Space : redirige vers Swagger UI."""
    return RedirectResponse(url="/docs")


@app.get(
    "/health",
    tags=["monitoring"],
    summary="État du service",
    responses={200: {"content": {"application/json": {"example": {"status": "ok"}}}}},
)
def health() -> dict[str, str]:
    """Renvoie `{"status": "ok"}` si l'API répond."""
    return {"status": "ok"}


@app.post(
    "/predict",
    tags=["prédiction"],
    summary="Prédire le départ d'un employé",
    responses={
        200: {
            "description": "Prédiction calculée et enregistrée.",
            "content": {"application/json": {"example": {
                "id_prediction": 1471, "probabilite_depart": 0.6367,
                "seuil": 0.41, "depart_predit": True,
            }}},
        },
        422: {
            "description": "Entrée invalide (champ manquant, valeur hors liste ou hors bornes, "
                           "champ inconnu). Rien n'est enregistré.",
            "content": {"application/json": {"example": EXEMPLE_422}},
        },
    },
)
def predict(
    employe: EmployeInput,
    modele: Annotated[dict, Depends(get_modele)],
    session: Annotated[Session, Depends(get_session)],
) -> PredictionOutput:
    """Estime la probabilité de départ d'un employé et enregistre la prédiction.

    - **probabilite_depart** : probabilité estimée par le modèle (0 à 1).
    - **depart_predit** : `true` si la probabilité atteint le seuil (0,41).
      Ce seuil privilégie la détection des départs : environ 8 départs réels
      sur 10 sont signalés, au prix de fausses alertes (≈ 3 alertes sur 10 justifiées).
    - Les entrées sont stockées dans la table `employes`, le résultat dans
      `predictions` (identifiant renvoyé dans **id_prediction**).
    """
    entrees = employe.model_dump()
    X = pd.DataFrame([entrees])[modele["colonnes_entree"]]
    proba = float(modele["pipeline"].predict_proba(X)[0, 1])
    seuil = modele["seuil"]
    depart = proba >= seuil

    prediction = Prediction(origine="prediction", depart=depart, probabilite=proba, seuil=seuil)
    session.add(Employe(**entrees, predictions=[prediction]))
    session.commit()

    return PredictionOutput(
        id_prediction=prediction.id,
        probabilite_depart=round(proba, 4),
        seuil=seuil,
        depart_predit=depart,
    )

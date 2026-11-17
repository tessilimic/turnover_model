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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Au démarrage : erreur visible tout de suite, 1re requête rapide.
    get_modele()
    creer_schema(get_engine())  # idempotent
    yield


app = FastAPI(
    title="Turnover API",
    description="API de prédiction du turnover des employés.",
    version="0.3.0",
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Page d'accueil du Space : redirige vers Swagger UI."""
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["monitoring"])
def health() -> dict[str, str]:
    """Vérifie que l'API est en ligne."""
    return {"status": "ok"}


@app.post("/predict", tags=["prédiction"])
def predict(
    employe: EmployeInput,
    modele: Annotated[dict, Depends(get_modele)],
    session: Annotated[Session, Depends(get_session)],
) -> PredictionOutput:
    """Estime la probabilité de départ d'un employé et enregistre la prédiction.

    Le départ est prédit si la probabilité atteint le seuil du modèle (0,41),
    choisi pour détecter un maximum de départs (F2).
    Les entrées sont stockées dans la table `employes`, le résultat dans `predictions`.
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

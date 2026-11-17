from contextlib import asynccontextmanager
from typing import Annotated

import pandas as pd
from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse

from app.model import get_modele
from app.schemas import EmployeInput, PredictionOutput


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_modele()  # chargé au démarrage : erreur visible tout de suite, 1re requête rapide
    yield


app = FastAPI(
    title="Turnover API",
    description="API de prédiction du turnover des employés.",
    version="0.2.0",
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
    employe: EmployeInput, modele: Annotated[dict, Depends(get_modele)]
) -> PredictionOutput:
    """Estime la probabilité de départ d'un employé.

    Le départ est prédit si la probabilité atteint le seuil du modèle (0,41),
    choisi pour détecter un maximum de départs (F2).
    """
    X = pd.DataFrame([employe.model_dump()])[modele["colonnes_entree"]]
    proba = float(modele["pipeline"].predict_proba(X)[0, 1])
    seuil = modele["seuil"]
    return PredictionOutput(
        probabilite_depart=round(proba, 4),
        seuil=seuil,
        depart_predit=proba >= seuil,
    )

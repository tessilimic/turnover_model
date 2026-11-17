"""Application FastAPI : routes de l'API de prédiction du turnover.

La documentation interactive (Swagger UI) est générée à partir de ce fichier
et de :mod:`app.schemas` ; elle est servie sur ``/docs``.
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Annotated

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.auth import (
    acces_prediction,
    authentifier,
    creer_jeton,
    duree_jeton,
    get_secret_jwt,
    utilisateur_courant,
)
from app.logs import configurer_logs
from app.model import get_modele
from app.schemas import EmployeInput, Jeton, PredictionOutput, UtilisateurCourant
from app.securite import entetes_securite
from app.tracabilite import erreur_validation, routeur_logs, tracer_requetes
from app.utilisateurs import creer_admin_initial
from src.db.models import Employe, Prediction, Utilisateur
from src.db.session import creer_schema, get_engine, get_session, tables_manquantes

configurer_logs()
journal = logging.getLogger("turnover.api")

DESCRIPTION = """
Estime le **risque de départ** d'un employé à partir de son profil RH
(SIRH, sondage interne, évaluations).

* Modèle : Random Forest (scikit-learn), seuil de décision **0,41**,
  choisi pour détecter un maximum de départs (F2).
* **Authentification** : obtenir un jeton avec `POST /token` (bouton *Authorize*),
  puis l'envoyer dans l'en-tête `Authorization: Bearer <jeton>`.
  Rôles : `rh` (prédire), `auditeur` (consulter le journal), `admin` (tout).
* Chaque prédiction est **enregistrée** en base (entrées et résultat), et chaque
  appel à `/predict`, même refusé, est tracé dans le journal des interactions
  (`GET /logs`), avec le compte à l'origine de l'appel.
* Chaque réponse porte un en-tête **X-Request-ID**, présent dans tous les logs.
* Documentation complète : guide utilisateur, fiche du modèle, architecture,
  sécurité et maintenance dans le dossier `docs/` du dépôt (site MkDocs).
"""

TAGS = [
    {"name": "authentification", "description": "Obtenir un jeton d'accès."},
    {"name": "prédiction", "description": "Estimer le risque de départ d'un employé (rôle rh ou admin)."},
    {"name": "traçabilité", "description": "Consulter le journal des appels au modèle "
                                           "(rôle auditeur ou admin)."},
    {"name": "monitoring", "description": "Vérifier que le service est en ligne (public)."},
]

EXEMPLE_422 = {
    "detail": [{
        "type": "literal_error",
        "loc": ["body", "poste"],
        "msg": "Input should be 'Assistant de Direction', 'Cadre Commercial', ...",
        "input": "Astronaute",
    }]
}
REPONSES_AUTH = {
    401: {"description": "Non authentifié : jeton absent, invalide ou expiré."},
    403: {"description": "Rôle insuffisant pour cette action."},
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Au démarrage : charge le modèle, prépare la clé des jetons, vérifie la base.

    * **PostgreSQL** : l'API (rôle ``turnover_api``) n'a pas le droit de créer des
      tables ; elle vérifie seulement que ``init_db`` a été lancé.
    * **SQLite** (Hugging Face, sans administrateur) : l'API crée les tables et le
      compte administrateur initial (``ADMIN_USERNAME`` / ``ADMIN_PASSWORD``).

    Une erreur de configuration empêche le démarrage : elle est visible tout de suite.
    """
    journal.info("démarrage de l'API", extra={"evenement": "api.demarrage", "version": app.version})
    get_modele()
    get_secret_jwt()
    engine = get_engine()
    if engine.dialect.name == "sqlite":
        creer_schema(engine)
        with Session(engine) as session:
            if creer_admin_initial(session):
                journal.info("compte administrateur initial créé",
                             extra={"evenement": "auth.admin_initial"})
    elif manquantes := tables_manquantes(engine):
        raise RuntimeError(f"Tables absentes ({', '.join(manquantes)}) : "
                           "lancer python -m src.db.init_db")
    yield
    journal.info("arrêt de l'API", extra={"evenement": "api.arret"})


app = FastAPI(
    title="Turnover API",
    summary="Prédiction du risque de départ des employés.",
    description=DESCRIPTION,
    version="1.0.0",
    openapi_tags=TAGS,
    lifespan=lifespan,
)
# Le dernier middleware ajouté s'exécute en premier : la traçabilité englobe tout.
app.middleware("http")(entetes_securite)
app.middleware("http")(tracer_requetes)
app.add_exception_handler(RequestValidationError, erreur_validation)
app.include_router(routeur_logs)


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
    """Renvoie `{"status": "ok"}` si l'API répond. Public, sans donnée."""
    return {"status": "ok"}


@app.post(
    "/token",
    tags=["authentification"],
    summary="Se connecter (obtenir un jeton)",
    responses={401: {"description": "Identifiant ou mot de passe incorrect, ou compte "
                                    "désactivé ou verrouillé (raison non précisée)."}},
)
def connexion(
    formulaire: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[Session, Depends(get_session)],
) -> Jeton:
    """Échange un identifiant et un mot de passe contre un jeton JWT.

    Le jeton est valable 30 minutes (par défaut) et s'envoie dans l'en-tête
    `Authorization: Bearer <jeton>`. Après 5 échecs, le compte est verrouillé
    15 minutes.
    """
    utilisateur = authentifier(session, formulaire.username, formulaire.password)
    if utilisateur is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Identifiant ou mot de passe incorrect.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Jeton(
        access_token=creer_jeton(utilisateur.identifiant, utilisateur.role),
        expires_in=int(duree_jeton().total_seconds()),
    )


@app.get("/moi", tags=["authentification"], summary="Compte connecté",
         responses={401: REPONSES_AUTH[401]})
def moi(utilisateur: Annotated[Utilisateur, Depends(utilisateur_courant)]) -> UtilisateurCourant:
    """Identifiant et rôle du compte associé au jeton."""
    return UtilisateurCourant.model_validate(utilisateur)


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
        **REPONSES_AUTH,
        422: {
            "description": "Entrée invalide (champ manquant, valeur hors liste ou hors bornes, "
                           "champ inconnu). Rien n'est enregistré.",
            "content": {"application/json": {"example": EXEMPLE_422}},
        },
    },
)
def predict(
    employe: EmployeInput,
    request: Request,
    utilisateur: Annotated[Utilisateur, Depends(acces_prediction)],
    modele: Annotated[dict, Depends(get_modele)],
    session: Annotated[Session, Depends(get_session)],
) -> PredictionOutput:
    """Estime la probabilité de départ d'un employé et enregistre la prédiction.

    Réservé aux rôles **rh** et **admin**.

    - **probabilite_depart** : probabilité estimée par le modèle (0 à 1).
    - **depart_predit** : `true` si la probabilité atteint le seuil (0,41).
      Ce seuil privilégie la détection des départs : environ 8 départs réels
      sur 10 sont signalés, au prix de fausses alertes (≈ 3 alertes sur 10 justifiées).
    - Les entrées sont stockées dans la table `employes`, le résultat dans
      `predictions` (identifiant renvoyé dans **id_prediction**).
    """
    entrees = employe.model_dump()
    # Pour le journal des interactions (écrit par le middleware après la réponse).
    request.state.entrees = entrees
    request.state.empreinte_modele = modele.get("empreinte")

    debut = time.perf_counter()
    X = pd.DataFrame([entrees])[modele["colonnes_entree"]]
    proba = float(modele["pipeline"].predict_proba(X)[0, 1])
    seuil = modele["seuil"]
    depart = proba >= seuil
    journal.info(
        "prédiction calculée",
        extra={"evenement": "modele.prediction", "probabilite": round(proba, 4),
               "seuil": seuil, "depart_predit": depart,
               "duree_ms": round((time.perf_counter() - debut) * 1000, 2),
               "empreinte_modele": modele.get("empreinte"),
               "utilisateur": utilisateur.identifiant},
    )

    prediction = Prediction(origine="prediction", depart=depart, probabilite=proba, seuil=seuil)
    session.add(Employe(**entrees, predictions=[prediction]))
    session.commit()
    request.state.prediction_id = prediction.id

    return PredictionOutput(
        id_prediction=prediction.id,
        probabilite_depart=round(proba, 4),
        seuil=seuil,
        depart_predit=depart,
    )

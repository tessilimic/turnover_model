"""Traçabilité : identifiant de requête, journal des interactions, consultation des logs.

* Chaque requête HTTP reçoit un ``request_id`` (repris de l'en-tête ``X-Request-ID``
  s'il est fourni et valide), renvoyé dans la réponse et présent dans tous les logs.
* Chaque appel à ``/predict`` (réussi, refusé ou en erreur) est enregistré dans la
  table ``interactions``.
* ``GET /logs`` permet de consulter ce journal, avec une clé d'API (``LOGS_API_KEY``).
"""

import logging
import os
import re
import secrets
import time
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Security
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.security import APIKeyHeader
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.logs import request_id_courant
from app.schemas import InteractionLog, PageInteractions
from src.db.models import Interaction
from src.db.session import get_engine, get_session

journal = logging.getLogger("turnover.api")

#: Routes dont chaque appel est enregistré dans la table ``interactions``.
ROUTES_JOURNALISEES = {"/predict"}

_REQUEST_ID_VALIDE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def request_id_depuis(en_tete: str | None) -> str:
    """Reprend l'identifiant fourni par le client s'il est sûr, sinon en génère un."""
    if en_tete and _REQUEST_ID_VALIDE.fullmatch(en_tete):
        return en_tete
    return str(uuid.uuid4())


# ---------------------------------------------------------------- middleware

async def tracer_requetes(request: Request, call_next):
    """Middleware HTTP : identifiant, durée, log de la requête, journal des interactions."""
    request_id = request_id_depuis(request.headers.get("X-Request-ID"))
    jeton = request_id_courant.set(request_id)
    debut = time.perf_counter()
    code_http = 500
    try:
        response = await call_next(request)
        code_http = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        journal.exception("erreur non gérée", extra={"evenement": "http.erreur"})
        raise
    finally:
        duree_ms = round((time.perf_counter() - debut) * 1000, 2)
        client = request.client.host if request.client else None
        journal.info(
            "requête HTTP",
            extra={"evenement": "http.requete", "methode": request.method,
                   "route": request.url.path, "code_http": code_http,
                   "duree_ms": duree_ms, "client": client},
        )
        if request.url.path in ROUTES_JOURNALISEES:
            etat = request.state
            await run_in_threadpool(enregistrer_interaction, {
                "request_id": request_id,
                "methode": request.method,
                "route": request.url.path,
                "code_http": code_http,
                "duree_ms": duree_ms,
                "client": client,
                "user_agent": (request.headers.get("user-agent") or "")[:300] or None,
                "entrees": getattr(etat, "entrees", None),
                "erreurs": getattr(etat, "erreurs", None),
                "prediction_id": getattr(etat, "prediction_id", None),
                "version_api": request.app.version,
                "empreinte_modele": getattr(etat, "empreinte_modele", None),
            })
        request_id_courant.reset(jeton)


def enregistrer_interaction(donnees: dict) -> None:
    """Écrit une ligne dans ``interactions``.

    Ne lève jamais d'exception : un échec du journal est lui-même journalisé
    mais ne doit pas faire échouer la réponse déjà calculée pour l'utilisateur.
    """
    try:
        with Session(get_engine()) as session:
            session.add(Interaction(**donnees))
            session.commit()
    except Exception:
        journal.exception(
            "échec de l'enregistrement de l'interaction",
            extra={"evenement": "interaction.erreur"},
        )


async def erreur_validation(request: Request, exc: RequestValidationError):
    """Garde le corps reçu et les erreurs pour le journal, puis répond 422 comme FastAPI."""
    corps = exc.body
    request.state.entrees = corps if isinstance(corps, dict) else (
        None if corps is None else {"brut": str(corps)[:2000]}
    )
    request.state.erreurs = jsonable_encoder(exc.errors())
    journal.warning(
        "entrée refusée",
        extra={"evenement": "http.validation",
               "champs": [".".join(map(str, e["loc"][1:])) for e in exc.errors()]},
    )
    return await request_validation_exception_handler(request, exc)


# ---------------------------------------------------------------- GET /logs

cle_api = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
    description="Clé de consultation des logs (variable LOGS_API_KEY du serveur).",
)


def verifier_cle_logs(cle: Annotated[str | None, Security(cle_api)]) -> None:
    """Autorise la consultation des logs.

    Raises:
        HTTPException: 403 si ``LOGS_API_KEY`` n'est pas défini (consultation
            désactivée), 401 si la clé est absente ou incorrecte.
    """
    attendue = os.getenv("LOGS_API_KEY")
    if not attendue:
        raise HTTPException(403, "Consultation des logs désactivée : LOGS_API_KEY non défini.")
    if not cle or not secrets.compare_digest(cle.encode(), attendue.encode()):
        journal.warning("accès aux logs refusé", extra={"evenement": "logs.acces_refuse"})
        raise HTTPException(401, "Clé d'API absente ou invalide (en-tête X-API-Key).")


routeur_logs = APIRouter(tags=["traçabilité"])


@routeur_logs.get(
    "/logs",
    summary="Consulter le journal des interactions",
    dependencies=[Depends(verifier_cle_logs)],
    responses={401: {"description": "Clé absente ou invalide."},
               403: {"description": "Consultation désactivée (LOGS_API_KEY non défini)."}},
)
def lire_logs(
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=500, description="Nombre de lignes")] = 50,
    offset: Annotated[int, Query(ge=0, description="Lignes à sauter (pagination)")] = 0,
    code_http: Annotated[int | None, Query(description="Ex. 200, 422")] = None,
    request_id: Annotated[str | None, Query(description="Une requête précise")] = None,
    depuis: Annotated[datetime | None, Query(description="Date ISO 8601 minimale")] = None,
    avec_entrees: Annotated[bool, Query(description="Inclure les données envoyées")] = False,
) -> PageInteractions:
    """Renvoie les appels à `/predict`, du plus récent au plus ancien.

    Protégé par l'en-tête **X-API-Key** (bouton *Authorize* de Swagger).
    Par défaut, les données envoyées (`entrees`, données RH) ne sont pas renvoyées.
    """
    filtres = []
    if code_http is not None:
        filtres.append(Interaction.code_http == code_http)
    if request_id is not None:
        filtres.append(Interaction.request_id == request_id)
    if depuis is not None:
        filtres.append(Interaction.cree_le >= depuis)

    total = session.scalar(select(func.count()).select_from(Interaction).where(*filtres))
    lignes = session.scalars(
        select(Interaction).where(*filtres).order_by(Interaction.id.desc())
        .limit(limit).offset(offset)
    ).all()

    items = [InteractionLog.model_validate(ligne) for ligne in lignes]
    if not avec_entrees:
        items = [item.model_copy(update={"entrees": None}) for item in items]
    journal.info("logs consultés", extra={"evenement": "logs.consultation", "lignes": len(items)})
    return PageInteractions(total=total, limit=limit, offset=offset, items=items)

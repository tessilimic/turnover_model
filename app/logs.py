"""Logs applicatifs structurés (une ligne JSON par événement).

Chaque ligne porte le ``request_id`` de la requête HTTP en cours : on peut ainsi
suivre une requête de bout en bout (HTTP -> modèle -> requêtes SQL -> réponse).

Configuration par variables d'environnement :

* ``LOG_LEVEL`` : niveau minimal (``INFO`` par défaut, ``DEBUG``, ``WARNING``...) ;
* ``LOG_FILE`` : si défini, écrit aussi dans ce fichier (rotation : 5 fichiers de 5 Mo).
"""

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

#: Identifiant de la requête HTTP en cours (``None`` hors requête).
request_id_courant: ContextVar[str | None] = ContextVar("request_id", default=None)

LOGGER_RACINE = "turnover"
_ATTRIBUTS_STANDARD = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "request_id"}
_fabrique_origine = logging.getLogRecordFactory()


def _fabrique_avec_request_id(*args, **kwargs) -> logging.LogRecord:
    """Ajoute le ``request_id`` courant à chaque enregistrement de log."""
    record = _fabrique_origine(*args, **kwargs)
    record.request_id = request_id_courant.get()
    return record


class FormateurJson(logging.Formatter):
    """Formate un enregistrement en une ligne JSON.

    Les champs passés via ``extra={...}`` sont ajoutés tels quels.
    """

    def format(self, record: logging.LogRecord) -> str:
        donnees = {
            "horodatage": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "niveau": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        donnees |= {k: v for k, v in vars(record).items() if k not in _ATTRIBUTS_STANDARD}
        if record.exc_info:
            donnees["exception"] = self.formatException(record.exc_info)
        return json.dumps(donnees, ensure_ascii=False, default=str)


def configurer_logs() -> logging.Logger:
    """Configure le logger ``turnover`` (sortie standard + fichier optionnel).

    Peut être appelée plusieurs fois : les handlers ne sont ajoutés qu'une fois.

    Returns:
        Le logger racine de l'application.
    """
    logging.setLogRecordFactory(_fabrique_avec_request_id)
    logger = logging.getLogger(LOGGER_RACINE)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    if getattr(logger, "_turnover_configure", False):
        return logger

    formateur = FormateurJson()
    sortie = logging.StreamHandler(sys.stdout)
    sortie.setFormatter(formateur)
    logger.addHandler(sortie)

    if fichier := os.getenv("LOG_FILE"):
        Path(fichier).parent.mkdir(parents=True, exist_ok=True)
        rotation = RotatingFileHandler(fichier, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
        rotation.setFormatter(formateur)
        logger.addHandler(rotation)

    logger._turnover_configure = True
    return logger

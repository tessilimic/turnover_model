"""Logs structurés et identifiant de requête, sans base de données."""

import json
import logging

import pytest

from app import logs
from app.logs import FormateurJson, configurer_logs, request_id_courant
from app.tracabilite import request_id_depuis


def enregistrement(message="bonjour", **extra) -> logging.LogRecord:
    configurer_logs()  # active l'ajout du request_id
    record = logging.getLogger("turnover.test").makeRecord(
        "turnover.test", logging.INFO, __file__, 1, message, (), None, extra=extra
    )
    return record


# ---------- Format JSON ----------

def test_une_ligne_json_avec_les_champs_de_base():
    ligne = json.loads(FormateurJson().format(enregistrement("requête SQL")))

    assert ligne["niveau"] == "INFO"
    assert ligne["logger"] == "turnover.test"
    assert ligne["message"] == "requête SQL"
    assert ligne["horodatage"].endswith("+00:00")  # UTC


def test_champs_extra_ajoutes():
    ligne = json.loads(FormateurJson().format(
        enregistrement(evenement="db.requete", duree_ms=1.5, sql="SELECT 1")
    ))

    assert ligne["evenement"] == "db.requete"
    assert ligne["duree_ms"] == 1.5
    assert ligne["sql"] == "SELECT 1"


def test_request_id_courant_ajoute_a_chaque_log():
    jeton = request_id_courant.set("req-123")
    try:
        ligne = json.loads(FormateurJson().format(enregistrement()))
    finally:
        request_id_courant.reset(jeton)

    assert ligne["request_id"] == "req-123"


def test_request_id_nul_hors_requete():
    assert json.loads(FormateurJson().format(enregistrement()))["request_id"] is None


def test_exception_incluse():
    try:
        raise ValueError("boum")
    except ValueError:
        import sys
        record = enregistrement()
        record.exc_info = sys.exc_info()

    ligne = json.loads(FormateurJson().format(record))

    assert "ValueError: boum" in ligne["exception"]


def test_accents_conserves():
    assert "Célibataire" in FormateurJson().format(enregistrement("Célibataire"))


# ---------- Configuration ----------

@pytest.fixture
def logger_neuf(monkeypatch):
    """Logger "turnover" vierge, restauré après le test."""
    logger = logging.getLogger(logs.LOGGER_RACINE)
    handlers, configure = logger.handlers[:], getattr(logger, "_turnover_configure", False)
    logger.handlers.clear()
    logger._turnover_configure = False
    yield logger
    for h in logger.handlers:
        h.close()
    logger.handlers[:] = handlers
    logger._turnover_configure = configure


def test_configuration_idempotente(logger_neuf):
    configurer_logs()
    configurer_logs()

    assert len(logger_neuf.handlers) == 1  # sortie standard seulement


def test_fichier_de_log_optionnel(logger_neuf, monkeypatch, tmp_path):
    fichier = tmp_path / "logs" / "api.log"
    monkeypatch.setenv("LOG_FILE", str(fichier))

    configurer_logs().info("écrit dans le fichier", extra={"evenement": "test"})
    for h in logger_neuf.handlers:
        h.flush()

    ligne = json.loads(fichier.read_text(encoding="utf-8").splitlines()[-1])
    assert ligne["message"] == "écrit dans le fichier"
    assert ligne["evenement"] == "test"


def test_niveau_configurable(logger_neuf, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "warning")

    assert configurer_logs().level == logging.WARNING


# ---------- Identifiant de requête ----------

@pytest.mark.parametrize("fourni", ["abc", "appel-rh_0042.v2", "a" * 64])
def test_request_id_client_valide_repris(fourni):
    assert request_id_depuis(fourni) == fourni


@pytest.mark.parametrize("fourni", [None, "", "a" * 65, "x; DROP TABLE", "é", "a\nb"])
def test_request_id_client_invalide_remplace(fourni):
    genere = request_id_depuis(fourni)

    assert genere != fourni
    assert len(genere) == 36

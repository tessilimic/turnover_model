"""Traçabilité de bout en bout : journal des interactions en base, GET /logs, logs techniques."""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.schemas import EXEMPLE_EMPLOYE
from src.db.models import Interaction, Prediction

@pytest.fixture(scope="module")
def client(engine, auth):
    with TestClient(app, headers=auth["rh"]) as c:  # rôle rh par défaut
        yield c


@pytest.fixture
def avec_cle(auth):
    """En-têtes d'un auditeur (seul rôle, avec admin, autorisé à lire le journal)."""
    return auth["auditeur"]


def interaction(engine, request_id: str) -> Interaction:
    with Session(engine) as session:
        return session.scalars(select(Interaction).where(Interaction.request_id == request_id)).one()


# ---------- Journal des interactions en base ----------

def test_prediction_reussie_tracee_et_reliee_a_la_prediction(client, engine):
    response = client.post("/predict", json=EXEMPLE_EMPLOYE)
    body = response.json()

    ligne = interaction(engine, response.headers["X-Request-ID"])

    assert ligne.code_http == 200
    assert ligne.prediction_id == body["id_prediction"]
    assert ligne.entrees == EXEMPLE_EMPLOYE
    assert ligne.erreurs is None
    assert ligne.empreinte_modele and len(ligne.empreinte_modele) == 12
    assert ligne.version_api == app.version
    with Session(engine) as session:
        assert session.get(Prediction, ligne.prediction_id).probabilite == pytest.approx(
            body["probabilite_depart"], abs=1e-4
        )


def test_appel_refuse_trace_sans_prediction(client, engine):
    response = client.post("/predict", json=EXEMPLE_EMPLOYE | {"poste": "Astronaute"})

    ligne = interaction(engine, response.headers["X-Request-ID"])

    assert ligne.code_http == 422
    assert ligne.prediction_id is None
    assert ligne.entrees["poste"] == "Astronaute"
    assert ligne.erreurs[0]["loc"] == ["body", "poste"]


def test_json_mal_forme_trace(client, engine):
    response = client.post(
        "/predict", content="{pas du json", headers={"Content-Type": "application/json"}
    )

    ligne = interaction(engine, response.headers["X-Request-ID"])

    assert ligne.code_http == 422
    assert ligne.erreurs


# ---------- GET /logs ----------

def test_logs_reserves_aux_auditeurs_et_admins(client, auth):
    sans_jeton = {"Authorization": ""}
    assert client.get("/logs", headers=sans_jeton).status_code == 401
    assert client.get("/logs", headers={"Authorization": "Bearer faux"}).status_code == 401
    assert client.get("/logs", headers=auth["rh"]).status_code == 403
    assert client.get("/logs", headers=auth["auditeur"]).status_code == 200
    assert client.get("/logs", headers=auth["admin"]).status_code == 200


def test_utilisateur_enregistre_dans_le_journal(client, avec_cle):
    client.post("/predict", json=EXEMPLE_EMPLOYE, headers={"X-Request-ID": "qui-1"})

    page = client.get("/logs", params={"request_id": "qui-1"}, headers=avec_cle).json()

    assert page["items"][0]["utilisateur"] == "rh.test"


def test_logs_retrouve_un_appel_par_request_id(client, avec_cle):
    client.post("/predict", json=EXEMPLE_EMPLOYE, headers={"X-Request-ID": "suivi-42"})

    page = client.get("/logs", params={"request_id": "suivi-42"}, headers=avec_cle).json()

    assert page["total"] == 1
    (item,) = page["items"]
    assert item["request_id"] == "suivi-42"
    assert item["code_http"] == 200
    assert item["entrees"] is None  # données RH masquées par défaut


def test_logs_avec_entrees_sur_demande(client, avec_cle):
    client.post("/predict", json=EXEMPLE_EMPLOYE, headers={"X-Request-ID": "suivi-43"})

    page = client.get(
        "/logs", params={"request_id": "suivi-43", "avec_entrees": True}, headers=avec_cle
    ).json()

    assert page["items"][0]["entrees"] == EXEMPLE_EMPLOYE


def test_logs_filtres_et_pagination(client, avec_cle):
    for _ in range(3):
        client.post("/predict", json=EXEMPLE_EMPLOYE | {"age": -1})

    page = client.get("/logs", params={"code_http": 422, "limit": 2}, headers=avec_cle).json()

    assert page["total"] >= 3
    assert len(page["items"]) == 2
    assert all(item["code_http"] == 422 for item in page["items"])
    assert page["items"][0]["id"] > page["items"][1]["id"]  # plus récent d'abord


def test_logs_limite_bornee(client, avec_cle):
    assert client.get("/logs", params={"limit": 501}, headers=avec_cle).status_code == 422


def test_consultation_des_logs_non_journalisee_en_base(client, engine, avec_cle):
    response = client.get("/logs", headers=avec_cle)

    with Session(engine) as session:
        assert session.scalars(
            select(Interaction).where(Interaction.request_id == response.headers["X-Request-ID"])
        ).first() is None


# ---------- Logs techniques : une requête suivie de bout en bout ----------

def test_logs_techniques_relies_par_request_id(client, caplog):
    caplog.set_level(logging.INFO, logger="turnover")

    client.post("/predict", json=EXEMPLE_EMPLOYE, headers={"X-Request-ID": "bout-en-bout"})

    evenements = [r.evenement for r in caplog.records
                  if getattr(r, "request_id", None) == "bout-en-bout"]
    assert "modele.prediction" in evenements
    assert "db.requete" in evenements       # INSERT employes / predictions / interactions
    assert "db.commit" in evenements
    assert "http.requete" in evenements


def test_valeurs_des_parametres_sql_jamais_journalisees(client, caplog):
    caplog.set_level(logging.INFO, logger="turnover")

    client.post("/predict", json=EXEMPLE_EMPLOYE | {"revenu_mensuel": 987654})

    assert not any("987654" in str(getattr(r, "sql", "")) for r in caplog.records)

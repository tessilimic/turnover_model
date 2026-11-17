"""Tests fonctionnels : l'API appelée en HTTP, avec le vrai modèle et une vraie base."""

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.model import get_modele
from app.schemas import EXEMPLE_EMPLOYE
from src.db.models import Employe, Prediction
from src.features import COLONNES_ENTREE


@pytest.fixture(scope="module")
def client(engine, auth):
    # "with" : exécute le démarrage (modèle, base) ; connecté avec le rôle rh par défaut.
    with TestClient(app, headers=auth["rh"]) as c:
        yield c


@pytest.fixture
def employe() -> dict:
    return dict(EXEMPLE_EMPLOYE)


# ---------- Routes de base ----------

def test_root_redirects_to_docs(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


def test_health_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_docs_are_available(client):
    response = client.get("/docs")

    assert response.status_code == 200


# ---------- /predict : cas valides ----------

def test_predict_renvoie_probabilite_seuil_et_decision(client, employe):
    response = client.post("/predict", json=employe)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"id_prediction", "probabilite_depart", "seuil", "depart_predit"}
    assert 0 <= body["probabilite_depart"] <= 1
    assert body["seuil"] == 0.41
    assert body["depart_predit"] == (body["probabilite_depart"] >= body["seuil"])


def test_predict_identique_au_pipeline(client, employe):
    modele = get_modele()
    attendu = modele["pipeline"].predict_proba(pd.DataFrame([employe]))[0, 1]

    body = client.post("/predict", json=employe).json()

    assert body["probabilite_depart"] == pytest.approx(attendu, abs=1e-4)


def test_predict_profil_a_risque_vs_profil_stable(client, employe):
    a_risque = employe | {
        "age": 22, "revenu_mensuel": 1500, "annee_experience_totale": 1,
        "heure_supplementaires": "Oui", "frequence_deplacement": "Frequent",
        "statut_marital": "Célibataire", "satisfaction_employee_environnement": 1,
        "satisfaction_employee_equilibre_pro_perso": 1, "nombre_participation_pee": 0,
    }
    stable = employe | {
        "age": 45, "revenu_mensuel": 12000, "annee_experience_totale": 20,
        "heure_supplementaires": "Non", "frequence_deplacement": "Aucun",
        "statut_marital": "Marié(e)", "satisfaction_employee_environnement": 4,
        "satisfaction_employee_equilibre_pro_perso": 4, "nombre_participation_pee": 2,
    }

    p_risque = client.post("/predict", json=a_risque).json()
    p_stable = client.post("/predict", json=stable).json()

    assert p_risque["probabilite_depart"] > p_stable["probabilite_depart"]
    assert p_risque["depart_predit"] is True
    assert p_stable["depart_predit"] is False


# ---------- /predict : enregistrement en base ----------

def test_predict_enregistre_entrees_et_sortie(client, engine, employe):
    body = client.post("/predict", json=employe).json()

    with Session(engine) as session:
        prediction = session.get(Prediction, body["id_prediction"])

        assert prediction.origine == "prediction"
        assert prediction.depart == body["depart_predit"]
        assert prediction.seuil == body["seuil"]
        assert prediction.probabilite == pytest.approx(body["probabilite_depart"], abs=1e-4)
        # Entrées liées par la clé étrangère
        stocke = prediction.employe
        assert stocke.id_employee is None  # pas un employé du jeu initial
        assert {col: getattr(stocke, col) for col in COLONNES_ENTREE} == employe


def test_chaque_appel_cree_une_nouvelle_ligne(client, engine, employe):
    def nb_predictions():
        with Session(engine) as session:
            return session.scalar(select(func.count()).select_from(Prediction))

    avant = nb_predictions()
    ids = {client.post("/predict", json=employe).json()["id_prediction"] for _ in range(3)}

    assert nb_predictions() == avant + 3
    assert len(ids) == 3


def test_requete_invalide_n_enregistre_rien(client, engine, employe):
    with Session(engine) as session:
        avant = session.scalar(select(func.count()).select_from(Employe))

    client.post("/predict", json=employe | {"genre": "X"})

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Employe)) == avant


# ---------- /predict : réponse HTTP aux entrées invalides (422) ----------
# Le détail des règles de validation est testé dans tests/unit/test_schemas.py.

def test_predict_refuse_champ_manquant(client, employe):
    del employe["age"]

    response = client.post("/predict", json=employe)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "age"]


@pytest.mark.parametrize(
    ("champ", "valeur"),
    [("poste", "Astronaute"), ("satisfaction_employee_equipe", 5), ("age", "quarante")],
)
def test_predict_refuse_valeur_invalide(client, employe, champ, valeur):
    employe[champ] = valeur

    response = client.post("/predict", json=employe)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", champ]


def test_predict_refuse_json_mal_forme(client):
    response = client.post(
        "/predict", content="{pas du json", headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 422


def test_methode_get_non_autorisee_sur_predict(client):
    assert client.get("/predict").status_code == 405

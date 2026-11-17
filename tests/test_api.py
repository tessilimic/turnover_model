from typing import get_args

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.model import get_modele
from app.schemas import EXEMPLE_EMPLOYE, EmployeInput
from src.features import BINAIRES, COLONNES_ENTREE, NOMINALES, ORDINALES


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # "with" : exécute le chargement du modèle au démarrage
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
    assert set(body) == {"probabilite_depart", "seuil", "depart_predit"}
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


# ---------- /predict : validation des entrées (422) ----------

def test_predict_refuse_champ_manquant(client, employe):
    del employe["age"]

    response = client.post("/predict", json=employe)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "age"]


@pytest.mark.parametrize(
    ("champ", "valeur"),
    [
        ("poste", "Astronaute"),               # modalité inconnue
        ("genre", "X"),
        ("satisfaction_employee_equipe", 5),   # hors échelle 1-4
        ("age", -3),
        ("revenu_mensuel", 0),
        ("augementation_salaire_precedente", "11 %"),  # attendu : 11
        ("age", "quarante"),
    ],
)
def test_predict_refuse_valeur_invalide(client, employe, champ, valeur):
    employe[champ] = valeur

    response = client.post("/predict", json=employe)

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", champ]


def test_predict_refuse_champ_inconnu(client, employe):
    employe["salaire"] = 3000  # faute de frappe : refusée plutôt qu'ignorée

    response = client.post("/predict", json=employe)

    assert response.status_code == 422


# ---------- Cohérence schéma <-> modèle ----------

def test_schema_contient_les_colonnes_du_modele():
    assert set(EmployeInput.model_fields) == set(COLONNES_ENTREE)
    assert get_modele()["colonnes_entree"] == COLONNES_ENTREE


def test_modalites_du_schema_identiques_a_celles_apprises():
    """Une modalité acceptée par l'API doit avoir été vue à l'entraînement."""
    prep = get_modele()["pipeline"].named_steps["prep"]
    apprises = {}
    for nom, encodeur, colonnes in prep.transformers_:
        if nom in ("nom", "bin", "ord"):
            apprises |= {c: set(cats) for c, cats in zip(colonnes, encodeur.categories_)}

    for colonne in NOMINALES + BINAIRES + ORDINALES:
        acceptees = set(get_args(EmployeInput.model_fields[colonne].annotation))
        assert acceptees == apprises[colonne], colonne


def test_exemple_swagger_valide():
    EmployeInput(**EXEMPLE_EMPLOYE)

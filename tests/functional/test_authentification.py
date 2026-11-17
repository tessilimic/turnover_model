"""Authentification de bout en bout : connexion, jetons, rôles, verrouillage, journal."""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import creer_jeton
from app.main import app
from app.schemas import EXEMPLE_EMPLOYE
from app.utilisateurs import creer_utilisateur
from src.db.models import Interaction, Utilisateur


@pytest.fixture(scope="module")
def client(engine):
    with TestClient(app) as c:  # sans jeton par défaut
        yield c


#: Mot de passe des comptes de test : même valeur que la fixture ``mot_de_passe_test``
#: (tests/conftest.py), vérifiée par test_mot_de_passe_identique_a_conftest.
MOT_DE_PASSE_TEST = "Motdepasse-de-test-42"


def test_mot_de_passe_identique_a_conftest(mot_de_passe_test):
    assert mot_de_passe_test == MOT_DE_PASSE_TEST


@pytest.fixture
def nouveau_compte(engine, mot_de_passe_test):
    """Fabrique de comptes jetables (pour les tests qui les modifient)."""
    compteur = iter(range(1000))

    def _creer(role="rh"):
        identifiant = f"jetable.{role}.{next(compteur)}.{id(compteur)}"
        with Session(engine) as session:
            creer_utilisateur(session, identifiant, mot_de_passe_test, role)
        return identifiant

    return _creer


def connexion(client, identifiant, mot_de_passe=None):
    mot_de_passe = mot_de_passe or MOT_DE_PASSE_TEST
    return client.post("/token", data={"username": identifiant, "password": mot_de_passe})


def entete(jeton: str) -> dict:
    return {"Authorization": f"Bearer {jeton}"}


# ---------- Connexion ----------

def test_connexion_renvoie_un_jeton_utilisable(client):
    response = connexion(client, "rh.test")

    assert response.status_code == 200
    corps = response.json()
    assert corps["token_type"] == "bearer"
    assert corps["expires_in"] == 30 * 60
    moi = client.get("/moi", headers=entete(corps["access_token"])).json()
    assert moi["identifiant"] == "rh.test"
    assert moi["role"] == "rh"
    assert moi["derniere_connexion"] is not None


@pytest.mark.parametrize(("identifiant", "mot_de_passe"), [
    ("rh.test", "mauvais-Mot-de-passe-1"),
    ("inconnu", None),  # None : le bon mot de passe d'un autre compte
])
def test_connexion_refusee_sans_dire_pourquoi(client, identifiant, mot_de_passe):
    response = connexion(client, identifiant, mot_de_passe)

    assert response.status_code == 401
    assert response.json()["detail"] == "Identifiant ou mot de passe incorrect."


def test_verrouillage_apres_5_echecs(client, nouveau_compte):
    identifiant = nouveau_compte()

    for _ in range(5):
        assert connexion(client, identifiant, "mauvais-Mot-de-passe-1").status_code == 401

    # Même le bon mot de passe est refusé pendant le verrouillage.
    assert connexion(client, identifiant).status_code == 401


def test_compte_desactive_perd_l_acces_immediatement(client, engine, nouveau_compte):
    identifiant = nouveau_compte()
    jeton = connexion(client, identifiant).json()["access_token"]
    assert client.get("/moi", headers=entete(jeton)).status_code == 200

    with Session(engine) as session:
        session.scalars(select(Utilisateur).where(Utilisateur.identifiant == identifiant)).one().actif = False
        session.commit()

    assert client.get("/moi", headers=entete(jeton)).status_code == 401  # jeton encore valide
    assert connexion(client, identifiant).status_code == 401


def test_changement_de_role_pris_en_compte_sans_nouveau_jeton(client, engine, nouveau_compte):
    identifiant = nouveau_compte("rh")
    jeton = connexion(client, identifiant).json()["access_token"]

    with Session(engine) as session:
        session.scalars(select(Utilisateur).where(Utilisateur.identifiant == identifiant)).one().role = "auditeur"
        session.commit()

    assert client.post("/predict", json=EXEMPLE_EMPLOYE, headers=entete(jeton)).status_code == 403


def test_jeton_d_un_compte_inexistant_refuse(client):
    assert client.get("/moi", headers=entete(creer_jeton("fantome", "admin"))).status_code == 401


# ---------- Droits par rôle ----------

@pytest.mark.parametrize(("role", "code_predict", "code_logs"), [
    ("rh", 200, 403),
    ("auditeur", 403, 200),
    ("admin", 200, 200),
])
def test_matrice_des_droits(client, auth, role, code_predict, code_logs):
    assert client.post("/predict", json=EXEMPLE_EMPLOYE, headers=auth[role]).status_code == code_predict
    assert client.get("/logs", headers=auth[role]).status_code == code_logs


def test_sans_jeton(client):
    response = client.post("/predict", json=EXEMPLE_EMPLOYE)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_routes_publiques(client):
    assert client.get("/health").status_code == 200
    assert client.get("/docs").status_code == 200


# ---------- Traçabilité et confidentialité ----------

def test_appel_non_authentifie_trace_sans_donnees(client, engine):
    response = client.post("/predict", json=EXEMPLE_EMPLOYE, headers={"X-Request-ID": "intrus-1"})

    with Session(engine) as session:
        ligne = session.scalars(select(Interaction).where(Interaction.request_id == "intrus-1")).one()
    assert response.status_code == 401
    assert ligne.code_http == 401
    assert ligne.utilisateur is None
    assert ligne.entrees is None  # les données d'un appel non authentifié ne sont pas conservées


def test_mot_de_passe_jamais_dans_les_logs(client, caplog):
    caplog.set_level(logging.DEBUG, logger="turnover")

    connexion(client, "rh.test")
    connexion(client, "rh.test", "Secret-a-ne-pas-logger-9")

    texte = " ".join(f"{r.getMessage()} {vars(r)}" for r in caplog.records)
    assert MOT_DE_PASSE_TEST not in texte
    assert "Secret-a-ne-pas-logger-9" not in texte
    assert "auth.refus" in texte  # l'échec est bien tracé, sans le mot de passe


def test_connexion_jamais_journalisee_en_base(client, engine):
    response = connexion(client, "rh.test")

    with Session(engine) as session:
        assert session.scalars(
            select(Interaction).where(Interaction.request_id == response.headers["X-Request-ID"])
        ).first() is None

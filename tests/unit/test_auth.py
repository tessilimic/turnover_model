"""Authentification : mots de passe, jetons, verrouillage, rôles, en-têtes (sans base)."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import auth
from app.auth import (
    creer_jeton,
    decoder_jeton,
    enregistrer_echec,
    enregistrer_succes,
    est_verrouille,
    exiger_role,
    get_secret_jwt,
    hacher_mot_de_passe,
    verifier_mot_de_passe,
    verifier_politique,
)
from app.main import app
from src.db.models import Utilisateur

MAINTENANT = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)


# ---------- Politique de mot de passe ----------

@pytest.mark.parametrize("mot_de_passe", ["Court-1", "toutenminuscules", "seulementlettresMAJ"])
def test_mot_de_passe_faible_refuse(mot_de_passe):
    with pytest.raises(ValueError):
        verifier_politique(mot_de_passe)


@pytest.mark.parametrize("mot_de_passe", ["Motdepasse-solide", "phrase de passe 2026", "Abcdefgh1234"])
def test_mot_de_passe_solide_accepte(mot_de_passe):
    verifier_politique(mot_de_passe)


# ---------- Hachage ----------

def test_empreinte_argon2id_et_jamais_le_mot_de_passe_en_clair():
    empreinte = hacher_mot_de_passe("Motdepasse-solide")

    assert empreinte.startswith("$argon2id$")
    assert "Motdepasse-solide" not in empreinte


def test_sel_aleatoire_deux_empreintes_differentes():
    assert hacher_mot_de_passe("Motdepasse-solide") != hacher_mot_de_passe("Motdepasse-solide")


def test_verification_du_mot_de_passe():
    empreinte = hacher_mot_de_passe("Motdepasse-solide")

    assert verifier_mot_de_passe(empreinte, "Motdepasse-solide") is True
    assert verifier_mot_de_passe(empreinte, "motdepasse-solide") is False
    assert verifier_mot_de_passe("pas-une-empreinte", "Motdepasse-solide") is False


# ---------- Jetons JWT ----------

def test_jeton_contient_identifiant_role_et_expiration():
    charge = decoder_jeton(creer_jeton("alice", "rh"))

    assert charge["sub"] == "alice"
    assert charge["role"] == "rh"
    assert charge["iss"] == "turnover-api"
    assert charge["exp"] - charge["iat"] == 30 * 60


def test_jeton_expire_refuse():
    ancien = creer_jeton("alice", "rh", maintenant=datetime.now(UTC) - timedelta(hours=1))

    with pytest.raises(jwt.ExpiredSignatureError):
        decoder_jeton(ancien)


def test_jeton_falsifie_refuse():
    entete, charge, signature = creer_jeton("alice", "rh").split(".")
    autre_charge = creer_jeton("admin", "admin").split(".")[1]

    with pytest.raises(jwt.InvalidSignatureError):
        decoder_jeton(f"{entete}.{autre_charge}.{signature}")


def test_jeton_signe_avec_une_autre_cle_refuse():
    faux = jwt.encode({"sub": "alice", "iss": "turnover-api", "iat": MAINTENANT,
                       "exp": datetime.now(UTC) + timedelta(minutes=5)},
                      "une-autre-cle-de-32-caracteres-au-moins", algorithm="HS256")

    with pytest.raises(jwt.InvalidSignatureError):
        decoder_jeton(faux)


def test_jeton_non_signe_alg_none_refuse():
    sans_signature = jwt.encode({"sub": "admin", "iss": "turnover-api", "iat": MAINTENANT,
                                 "exp": datetime.now(UTC) + timedelta(minutes=5)},
                                key=None, algorithm="none")

    with pytest.raises(jwt.InvalidTokenError):
        decoder_jeton(sans_signature)


def test_secret_trop_court_refuse(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "court")
    get_secret_jwt.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="32"):
            get_secret_jwt()
    finally:
        monkeypatch.undo()
        get_secret_jwt.cache_clear()


def test_secret_aleatoire_si_absent(monkeypatch):
    monkeypatch.delenv("JWT_SECRET")
    get_secret_jwt.cache_clear()
    try:
        assert len(get_secret_jwt()) >= 32
    finally:
        monkeypatch.undo()
        get_secret_jwt.cache_clear()


# ---------- Verrouillage ----------

def compte(**champs) -> Utilisateur:
    return Utilisateur(**{"identifiant": "alice", "role": "rh", "actif": True,
                          "echecs_connexion": 0} | champs)


def test_verrouillage_apres_5_echecs():
    alice = compte()

    for _ in range(4):
        enregistrer_echec(alice, MAINTENANT)
    assert not est_verrouille(alice, MAINTENANT)

    enregistrer_echec(alice, MAINTENANT)
    assert est_verrouille(alice, MAINTENANT)
    assert est_verrouille(alice, MAINTENANT + timedelta(minutes=14))
    assert not est_verrouille(alice, MAINTENANT + timedelta(minutes=16))


def test_succes_remet_les_compteurs_a_zero():
    alice = compte(echecs_connexion=3, verrouille_jusqu_a=MAINTENANT - timedelta(minutes=1))

    enregistrer_succes(alice, MAINTENANT)

    assert alice.echecs_connexion == 0
    assert alice.verrouille_jusqu_a is None
    assert alice.derniere_connexion == MAINTENANT


def test_verrouillage_lu_sans_fuseau_sqlite():
    alice = compte(verrouille_jusqu_a=(MAINTENANT + timedelta(minutes=5)).replace(tzinfo=None))

    assert est_verrouille(alice, MAINTENANT)


# ---------- Rôles ----------

@pytest.mark.parametrize(("role", "autorise"), [("rh", True), ("admin", True), ("auditeur", False)])
def test_controle_par_role(role, autorise):
    verifier = exiger_role("rh", "admin")
    utilisateur = compte(role=role)

    if autorise:
        assert verifier(utilisateur) is utilisateur
    else:
        with pytest.raises(HTTPException) as exc:
            verifier(utilisateur)
        assert exc.value.status_code == 403


def test_matrice_des_droits():
    """Qui peut prédire, qui peut lire le journal (voir docs/securite.md)."""
    def roles_autorises(dependance):
        return {r for r in auth.ROLES if _autorise(dependance, r)}

    def _autorise(dependance, role):
        try:
            dependance(Utilisateur(identifiant="x", role=role, actif=True))
            return True
        except HTTPException:
            return False

    assert roles_autorises(auth.acces_prediction) == {"rh", "admin"}
    assert roles_autorises(auth.acces_logs) == {"auditeur", "admin"}


# ---------- En-têtes de sécurité ----------

def test_entetes_de_securite_sur_les_reponses_api():
    response = TestClient(app).get("/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert "max-age" in response.headers["Strict-Transport-Security"]


@pytest.mark.parametrize("chemin", ["/docs", "/redoc", "/docs/oauth2-redirect"])
def test_documentation_affichable_dans_l_onglet_app_du_space(chemin):
    """L'onglet App de Hugging Face affiche Swagger dans un cadre de huggingface.co.

    La politique stricte (default-src 'none', X-Frame-Options: DENY) donnerait une
    page blanche : scripts du CDN bloqués, affichage en cadre refusé.
    """
    response = TestClient(app).get(chemin)

    assert response.headers["Content-Security-Policy"] == "frame-ancestors 'self' https://huggingface.co"
    assert "X-Frame-Options" not in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_redirection_d_accueil_affichable_dans_un_cadre():
    """L'onglet App charge d'abord « / », qui redirige vers /docs."""
    response = TestClient(app).get("/", follow_redirects=False)

    assert response.status_code == 307
    assert "X-Frame-Options" not in response.headers
    assert "https://huggingface.co" in response.headers["Content-Security-Policy"]


@pytest.mark.parametrize("chemin", ["/health", "/openapi.json", "/documents"])
def test_hors_documentation_jamais_dans_un_cadre(chemin):
    headers = TestClient(app).get(chemin).headers

    assert headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["Content-Security-Policy"]


def test_origines_du_cadre_configurables(monkeypatch):
    monkeypatch.setenv("FRAME_ANCESTORS", "https://intranet.exemple.fr")

    csp = TestClient(app).get("/docs").headers["Content-Security-Policy"]

    assert csp == "frame-ancestors 'self' https://intranet.exemple.fr"


def test_routes_protegees_sans_jeton():
    client = TestClient(app)

    assert client.post("/predict", json={}).status_code == 401
    assert client.get("/logs").status_code == 401
    assert client.get("/moi").status_code == 401
    assert client.get("/predict").headers.get("WWW-Authenticate") is None  # 405, pas 401

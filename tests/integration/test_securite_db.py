"""Sécurité côté base : comptes, contraintes, et droits réels des rôles PostgreSQL."""

import os

import pytest
from psycopg.errors import InsufficientPrivilege
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.auth import verifier_mot_de_passe
from app.schemas import EXEMPLE_EMPLOYE
from app.utilisateurs import creer_utilisateur, main as cli
from src.db.models import Employe, Interaction, Prediction, Utilisateur
from src.db.session import appliquer_roles
from src.train import charger_donnees


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s
        s.rollback()


def compte(session, identifiant) -> Utilisateur:
    return session.scalars(select(Utilisateur).where(Utilisateur.identifiant == identifiant)).one()


# ---------- Comptes ----------

def test_mot_de_passe_stocke_en_empreinte_argon2id(session):
    creer_utilisateur(session, "empreinte.test", "Motdepasse-solide-1", "rh")

    stocke = compte(session, "empreinte.test").mot_de_passe_hash
    assert stocke.startswith("$argon2id$")
    assert verifier_mot_de_passe(stocke, "Motdepasse-solide-1")


def test_la_base_refuse_un_mot_de_passe_en_clair(session):
    session.add(Utilisateur(identifiant="clair.test", role="rh", mot_de_passe_hash="motdepasse"))

    with pytest.raises(IntegrityError):
        session.commit()


def test_la_base_refuse_un_role_inconnu(session):
    session.add(Utilisateur(identifiant="role.test", role="superadmin",
                            mot_de_passe_hash="$argon2id$v=19$m=65536,t=3,p=4$xxx$yyy"))

    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize(("identifiant", "mot_de_passe", "role"), [
    ("Majuscules", "Motdepasse-solide-1", "rh"),   # identifiant invalide
    ("ok.test", "faible", "rh"),                    # mot de passe trop faible
    ("ok.test", "Motdepasse-solide-1", "root"),     # rôle inconnu
    ("rh.test", "Motdepasse-solide-1", "rh"),       # identifiant déjà pris
])
def test_creation_de_compte_refusee(session, identifiant, mot_de_passe, role):
    with pytest.raises(ValueError):
        creer_utilisateur(session, identifiant, mot_de_passe, role)


# ---------- Ligne de commande ----------

def test_cycle_de_vie_d_un_compte_en_ligne_de_commande(engine, monkeypatch, capsys):
    monkeypatch.setenv("MDP_CLI", "Motdepasse-cli-2026")
    monkeypatch.setenv("MDP_CLI_2", "Nouveau-motdepasse-2026")

    assert cli(["creer", "cli.test", "--role", "auditeur", "--mot-de-passe-env", "MDP_CLI"]) == 0
    assert cli(["desactiver", "cli.test"]) == 0
    assert cli(["mot-de-passe", "cli.test", "--mot-de-passe-env", "MDP_CLI_2"]) == 0
    assert cli(["lister"]) == 0
    assert "cli.test" in capsys.readouterr().out

    with Session(engine) as session:
        utilisateur = compte(session, "cli.test")
        assert utilisateur.role == "auditeur"
        assert utilisateur.actif is False
        assert verifier_mot_de_passe(utilisateur.mot_de_passe_hash, "Nouveau-motdepasse-2026")

    assert cli(["creer", "cli.test", "--role", "rh", "--mot-de-passe-env", "MDP_CLI"]) == 1  # doublon
    assert cli(["desactiver", "inconnu.test"]) == 1


# ---------- Rôles PostgreSQL (moindre privilège) ----------

ROLES_PG = os.getenv("TEST_ROLES_PG") == "1"
pytestmark_pg = pytest.mark.skipif(
    not ROLES_PG,
    reason="PostgreSQL requis et TEST_ROLES_PG=1 (redéfinit les mots de passe des rôles du serveur)",
)
MDP_ROLES = {"turnover_api": "mdp-api-test-123456", "turnover_ml": "mdp-ml-test-123456",
             "turnover_auditeur": "mdp-auditeur-test-123456"}


@pytest.fixture(scope="module")
def connexions(engine):
    """Une connexion par rôle applicatif, après application de sql/05_roles.sql."""
    variables = {"turnover_api": "TURNOVER_API_DB_PASSWORD", "turnover_ml": "TURNOVER_ML_DB_PASSWORD",
                 "turnover_auditeur": "TURNOVER_AUDITEUR_DB_PASSWORD"}
    anciennes = {v: os.environ.get(v) for v in variables.values()}
    os.environ.update({variables[r]: mdp for r, mdp in MDP_ROLES.items()})
    try:
        assert set(appliquer_roles(engine)) == set(MDP_ROLES)
    finally:
        for variable, valeur in anciennes.items():
            if valeur is None:
                os.environ.pop(variable, None)
            else:
                os.environ[variable] = valeur

    moteurs = {role: create_engine(engine.url.set(username=role, password=mdp))
               for role, mdp in MDP_ROLES.items()}
    yield moteurs
    for moteur in moteurs.values():
        moteur.dispose()


def refuse(moteur, requete: str) -> bool:
    """True si PostgreSQL refuse la requête faute de droits (SQLSTATE 42501)."""
    try:
        with moteur.begin() as conn:
            conn.execute(text(requete))
    except ProgrammingError as erreur:
        return isinstance(erreur.orig, InsufficientPrivilege)
    return False


@pytestmark_pg
def test_api_peut_faire_son_travail(connexions):
    """Exactement les opérations de /predict, du journal et de la connexion."""
    with Session(connexions["turnover_api"], expire_on_commit=False) as session:
        prediction = Prediction(origine="prediction", depart=True, probabilite=0.7, seuil=0.41)
        session.add(Employe(**EXEMPLE_EMPLOYE, predictions=[prediction]))
        session.commit()
        session.add(Interaction(request_id="role-api-1", methode="POST", route="/predict",
                                code_http=200, duree_ms=1.0, version_api="test",
                                prediction_id=prediction.id))
        session.commit()
        assert session.scalars(select(Interaction.request_id)).first()  # GET /logs
        utilisateur = compte(session, "rh.test")                         # authentification
        utilisateur.echecs_connexion = 0
        session.commit()


@pytestmark_pg
@pytest.mark.parametrize("requete", [
    "SELECT age, revenu_mensuel FROM employes",                 # ne relit pas les données RH
    "UPDATE predictions SET depart = NOT depart",               # résultats non modifiables
    "DELETE FROM predictions",
    "DELETE FROM interactions",                                  # journal en ajout seul
    "UPDATE utilisateurs SET role = 'admin'",                   # ne peut pas s'élever
    "UPDATE utilisateurs SET mot_de_passe_hash = '$argon2id$x'",
    "INSERT INTO utilisateurs (identifiant, mot_de_passe_hash, role) VALUES ('x', '$argon2id$x', 'admin')",
    "CREATE TABLE intrus (id int)",
    "DROP TABLE interactions",
])
def test_api_ne_peut_rien_faire_d_autre(connexions, requete):
    assert refuse(connexions["turnover_api"], requete)


@pytestmark_pg
def test_entrainement_en_lecture_seule(connexions):
    assert len(charger_donnees(connexions["turnover_ml"])) == 1470
    assert refuse(connexions["turnover_ml"], "DELETE FROM employes")
    assert refuse(connexions["turnover_ml"], "SELECT * FROM interactions")
    assert refuse(connexions["turnover_ml"], "SELECT * FROM utilisateurs")


@pytestmark_pg
def test_auditeur_sans_donnees_rh(connexions):
    auditeur = connexions["turnover_auditeur"]
    with auditeur.connect() as conn:
        conn.execute(text("SELECT request_id, code_http, utilisateur FROM interactions"))
        conn.execute(text("SELECT probabilite, depart FROM predictions"))

    assert refuse(auditeur, "SELECT entrees FROM interactions")
    assert refuse(auditeur, "SELECT client FROM interactions")
    assert refuse(auditeur, "SELECT * FROM employes")
    assert refuse(auditeur, "SELECT * FROM utilisateurs")
    assert refuse(auditeur, "DELETE FROM interactions")

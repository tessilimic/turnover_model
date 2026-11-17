import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.schemas import EXEMPLE_EMPLOYE
from src.db.init_db import charger_csv_en_base, lire_csv
from src.db.models import Base, Employe, Prediction
from src.features import CIBLE, COLONNES_ENTREE


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s
        s.rollback()


def compter(session, *conditions) -> int:
    return session.scalar(select(func.count()).select_from(Prediction).where(*conditions))


# ---------- Fusion des CSV ----------

def test_lire_csv_fusionne_les_3_fichiers():
    df = lire_csv()

    assert len(df) == 1470
    assert df["id_employee"].is_unique
    assert set(COLONNES_ENTREE + ["id_employee", CIBLE]) == set(df.columns)


# ---------- Schéma ----------

@pytest.mark.parametrize("table", ["employes", "predictions"])
def test_colonnes_en_base_identiques_a_l_orm(engine, table):
    """Le schéma réellement créé (fichier SQL sur PostgreSQL) correspond aux modèles ORM."""
    en_base = {c["name"] for c in inspect(engine).get_columns(table)}

    assert en_base == set(Base.metadata.tables[table].columns.keys())


def test_cle_etrangere_entre_les_deux_tables(engine):
    (fk,) = inspect(engine).get_foreign_keys("predictions")

    assert fk["referred_table"] == "employes"
    assert fk["constrained_columns"] == ["employe_id"]


# ---------- Jeu initial ----------

def test_jeu_initial_charge(session):
    df = lire_csv()

    nb_employes = session.scalar(
        select(func.count()).select_from(Employe).where(Employe.id_employee.is_not(None))
    )
    assert nb_employes == 1470
    assert compter(session, Prediction.origine == "observation") == 1470
    assert compter(session, Prediction.origine == "observation", Prediction.depart) == (
        df[CIBLE].eq("Oui").sum()
    )


def test_observations_sans_probabilite_ni_seuil(session):
    assert compter(
        session,
        Prediction.origine == "observation",
        Prediction.probabilite.is_not(None) | Prediction.seuil.is_not(None),
    ) == 0


def test_chargement_idempotent(engine, session):
    assert charger_csv_en_base(engine) == 0
    assert compter(session, Prediction.origine == "observation") == 1470


def test_employe_relie_a_son_observation(session):
    employe = session.scalars(select(Employe).where(Employe.id_employee == 1)).one()

    (observation,) = employe.predictions
    assert observation.origine == "observation"
    assert observation.depart is True  # employé 1 : a_quitte_l_entreprise = "Oui"
    assert employe.augementation_salaire_precedente == 11  # "11 %" nettoyé


# ---------- Contraintes ----------

def nouvel_employe(**prediction) -> Employe:
    return Employe(**EXEMPLE_EMPLOYE, predictions=[Prediction(**prediction)])


@pytest.mark.parametrize(
    "prediction",
    [
        {"origine": "observation", "depart": True, "probabilite": 0.8, "seuil": 0.41},
        {"origine": "prediction", "depart": True},                       # sans proba ni seuil
        {"origine": "prediction", "depart": True, "probabilite": 1.5, "seuil": 0.41},
        {"origine": "autre", "depart": True},
    ],
)
def test_contraintes_refusent_une_ligne_incoherente(session, prediction):
    session.add(nouvel_employe(**prediction))

    with pytest.raises(IntegrityError):
        session.commit()


def test_cle_etrangere_refuse_un_employe_inexistant(session):
    session.add(Prediction(employe_id=999_999, origine="observation", depart=False))

    with pytest.raises(IntegrityError):
        session.commit()


def test_une_seule_observation_par_employe(session):
    employe = session.scalars(select(Employe).where(Employe.id_employee == 2)).one()
    employe.predictions.append(Prediction(origine="observation", depart=True))

    with pytest.raises(IntegrityError):
        session.commit()


def test_suppression_employe_supprime_ses_predictions(session):
    employe = nouvel_employe(origine="prediction", depart=False, probabilite=0.2, seuil=0.41)
    session.add(employe)
    session.commit()
    id_employe = employe.id

    session.delete(employe)
    session.commit()

    assert compter(session, Prediction.employe_id == id_employe) == 0

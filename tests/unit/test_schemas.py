"""Validation des entrées et sorties de l'API (Pydantic), sans passer par HTTP."""

import pytest
from pydantic import ValidationError

from app.schemas import EXEMPLE_EMPLOYE, EmployeInput, PredictionOutput


@pytest.fixture
def employe() -> dict:
    return dict(EXEMPLE_EMPLOYE)


def champs_en_erreur(exc: ValidationError) -> set[str]:
    return {err["loc"][0] for err in exc.errors()}


# ---------- EmployeInput : cas valides ----------

def test_exemple_swagger_valide(employe):
    assert EmployeInput(**employe).model_dump() == employe


@pytest.mark.parametrize(
    ("champ", "valeur"),
    [
        ("satisfaction_employee_equipe", 1),       # bornes incluses
        ("satisfaction_employee_equipe", 4),
        ("niveau_education", 5),
        ("annee_experience_totale", 0),
        ("augementation_salaire_precedente", 0),
        ("frequence_deplacement", "Aucun"),
        ("statut_marital", "Divorcé(e)"),           # accents acceptés
    ],
)
def test_valeurs_limites_acceptees(employe, champ, valeur):
    assert getattr(EmployeInput(**employe | {champ: valeur}), champ) == valeur


def test_entier_envoye_en_texte_est_converti(employe):
    # Mode "lax" de Pydantic : "41" -> 41
    assert EmployeInput(**employe | {"age": "41"}).age == 41


# ---------- EmployeInput : cas refusés ----------

@pytest.mark.parametrize(
    ("champ", "valeur"),
    [
        ("poste", "Astronaute"),                    # modalité inconnue
        ("genre", "X"),
        ("genre", "f"),                             # sensible à la casse
        ("heure_supplementaires", "Yes"),
        ("frequence_deplacement", "Fréquent"),      # orthographe du jeu de données : "Frequent"
        ("satisfaction_employee_equipe", 0),        # échelle 1-4
        ("satisfaction_employee_equipe", 5),
        ("note_evaluation_precedente", 5),
        ("niveau_education", 6),
        ("age", 15),
        ("age", 81),
        ("revenu_mensuel", 0),
        ("distance_domicile_travail", -1),
        ("augementation_salaire_precedente", 101),
        ("augementation_salaire_precedente", "11 %"),
        ("age", "quarante"),
        ("age", 41.5),                              # entier attendu
        ("age", None),
    ],
)
def test_valeur_invalide_refusee(employe, champ, valeur):
    with pytest.raises(ValidationError) as exc:
        EmployeInput(**employe | {champ: valeur})

    assert champs_en_erreur(exc.value) == {champ}


@pytest.mark.parametrize("champ", list(EXEMPLE_EMPLOYE))
def test_chaque_champ_est_obligatoire(employe, champ):
    del employe[champ]

    with pytest.raises(ValidationError) as exc:
        EmployeInput(**employe)

    assert champs_en_erreur(exc.value) == {champ}


def test_champ_inconnu_refuse(employe):
    with pytest.raises(ValidationError) as exc:
        EmployeInput(**employe | {"salaire": 3000})

    assert champs_en_erreur(exc.value) == {"salaire"}


def test_plusieurs_erreurs_signalees_ensemble(employe):
    with pytest.raises(ValidationError) as exc:
        EmployeInput(**employe | {"age": -1, "genre": "X"})

    assert champs_en_erreur(exc.value) == {"age", "genre"}


# ---------- PredictionOutput ----------

def test_sortie_valide():
    sortie = PredictionOutput(id_prediction=1, probabilite_depart=0.5, seuil=0.41, depart_predit=True)

    assert sortie.model_dump() == {
        "id_prediction": 1, "probabilite_depart": 0.5, "seuil": 0.41, "depart_predit": True,
    }


@pytest.mark.parametrize("proba", [-0.01, 1.01])
def test_sortie_refuse_probabilite_hors_0_1(proba):
    with pytest.raises(ValidationError):
        PredictionOutput(id_prediction=1, probabilite_depart=proba, seuil=0.41, depart_predit=True)

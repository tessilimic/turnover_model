import pandas as pd
import pytest

from src.features import COLONNES_ENTREE, NOUVELLES_FEATURES, NUMERIQUES, ajouter_features


@pytest.fixture
def employe() -> pd.DataFrame:
    return pd.DataFrame([{
        "age": 30,
        "revenu_mensuel": 3000,
        "nombre_experiences_precedentes": 2,
        "annee_experience_totale": 5,
        "annees_dans_le_poste_actuel": 3,
        "annees_depuis_la_derniere_promotion": 2,
        "satisfaction_employee_environnement": 1,
        "satisfaction_employee_nature_travail": 2,
        "satisfaction_employee_equipe": 3,
        "satisfaction_employee_equilibre_pro_perso": 4,
        "heure_supplementaires": "Oui",
        "frequence_deplacement": "Frequent",
    }])


def test_ajouter_features_calcule_les_valeurs(employe):
    ligne = ajouter_features(employe).iloc[0]

    assert ligne["satisfaction_moyenne"] == 2.5
    assert ligne["satisfaction_min"] == 1
    assert ligne["revenu_par_annee_exp"] == 500  # 3000 / (5 + 1)
    assert ligne["taux_mobilite"] == pytest.approx(2 / 6)
    assert ligne["age_debut_carriere"] == 25
    assert ligne["part_poste_sans_promo"] == 0.5  # 2 / (3 + 1)
    assert ligne["surcharge"] == 1


@pytest.mark.parametrize(
    ("heures_sup", "deplacement"),
    [("Non", "Frequent"), ("Oui", "Occasionnel"), ("Non", "Aucun")],
)
def test_surcharge_exige_heures_sup_et_deplacements_frequents(employe, heures_sup, deplacement):
    employe["heure_supplementaires"] = heures_sup
    employe["frequence_deplacement"] = deplacement

    assert ajouter_features(employe).iloc[0]["surcharge"] == 0


def test_debutant_sans_experience_ne_divise_pas_par_zero(employe):
    employe["annee_experience_totale"] = 0
    employe["annees_dans_le_poste_actuel"] = 0

    ligne = ajouter_features(employe).iloc[0]

    assert ligne["revenu_par_annee_exp"] == 3000
    assert ligne["part_poste_sans_promo"] == 2


def test_ajouter_features_ne_modifie_pas_l_entree(employe):
    colonnes_avant = list(employe.columns)

    ajouter_features(employe)

    assert list(employe.columns) == colonnes_avant


def test_listes_de_colonnes_coherentes():
    assert len(COLONNES_ENTREE) == len(set(COLONNES_ENTREE)) == 24
    assert set(NOUVELLES_FEATURES) <= set(NUMERIQUES)
    assert not set(NOUVELLES_FEATURES) & set(COLONNES_ENTREE)

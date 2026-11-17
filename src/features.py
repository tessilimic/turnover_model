"""Colonnes du modèle et création des features (repris du notebook)."""

import pandas as pd

CIBLE = "a_quitte_l_entreprise"

# Colonnes retirées lors du nettoyage
COLONNES_CONSTANTES = [
    "nombre_heures_travailless",
    "nombre_employee_sous_responsabilite",
    "ayant_enfants",
]
COLONNES_CORRELEES = [
    "niveau_hierarchique_poste",
    "note_evaluation_actuelle",
    "annees_dans_l_entreprise",
]

# Colonnes brutes attendues en entrée du modèle (et donc de l'API).
# L'ordre est celui du notebook : il conditionne l'ordre des features vues
# par la forêt, donc la reproductibilité des résultats.
NOMINALES = ["statut_marital", "departement", "poste", "domaine_etude"]
BINAIRES = ["genre", "heure_supplementaires"]
ORDINALES = ["frequence_deplacement"]
ORDRE_DEPLACEMENT = ["Aucun", "Occasionnel", "Frequent"]

NUMERIQUES_BRUTES = [
    "age",
    "revenu_mensuel",
    "nombre_experiences_precedentes",
    "annee_experience_totale",
    "annees_dans_le_poste_actuel",
    "nombre_participation_pee",
    "nb_formations_suivies",
    "distance_domicile_travail",
    "niveau_education",
    "annees_depuis_la_derniere_promotion",
    "annes_sous_responsable_actuel",
    "satisfaction_employee_environnement",
    "note_evaluation_precedente",
    "satisfaction_employee_nature_travail",
    "satisfaction_employee_equipe",
    "satisfaction_employee_equilibre_pro_perso",
    "augementation_salaire_precedente",
]

COLONNES_ENTREE = [
    "age",
    "genre",
    "revenu_mensuel",
    "statut_marital",
    "departement",
    "poste",
    "nombre_experiences_precedentes",
    "annee_experience_totale",
    "annees_dans_le_poste_actuel",
    "nombre_participation_pee",
    "nb_formations_suivies",
    "distance_domicile_travail",
    "niveau_education",
    "domaine_etude",
    "frequence_deplacement",
    "annees_depuis_la_derniere_promotion",
    "annes_sous_responsable_actuel",
    "satisfaction_employee_environnement",
    "note_evaluation_precedente",
    "satisfaction_employee_nature_travail",
    "satisfaction_employee_equipe",
    "satisfaction_employee_equilibre_pro_perso",
    "heure_supplementaires",
    "augementation_salaire_precedente",
]

SATISFACTIONS = [
    "satisfaction_employee_environnement",
    "satisfaction_employee_nature_travail",
    "satisfaction_employee_equipe",
    "satisfaction_employee_equilibre_pro_perso",
]

NOUVELLES_FEATURES = [
    "satisfaction_moyenne",
    "satisfaction_min",
    "revenu_par_annee_exp",
    "taux_mobilite",
    "age_debut_carriere",
    "part_poste_sans_promo",
    "surcharge",
]

NUMERIQUES = NUMERIQUES_BRUTES + NOUVELLES_FEATURES


def ajouter_features(X: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les 7 features créées dans le notebook, sans modifier X."""
    X = X.copy()
    X["satisfaction_moyenne"] = X[SATISFACTIONS].mean(axis=1)
    # au moins un point de mécontentement fort
    X["satisfaction_min"] = X[SATISFACTIONS].min(axis=1)
    # +1 : évite la division par zéro pour les débutants
    X["revenu_par_annee_exp"] = X["revenu_mensuel"] / (X["annee_experience_totale"] + 1)
    X["taux_mobilite"] = X["nombre_experiences_precedentes"] / (X["annee_experience_totale"] + 1)
    X["age_debut_carriere"] = X["age"] - X["annee_experience_totale"]
    X["part_poste_sans_promo"] = X["annees_depuis_la_derniere_promotion"] / (
        X["annees_dans_le_poste_actuel"] + 1
    )
    X["surcharge"] = (
        (X["heure_supplementaires"] == "Oui") & (X["frequence_deplacement"] == "Frequent")
    ).astype(int)
    return X

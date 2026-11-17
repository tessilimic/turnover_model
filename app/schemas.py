"""Format des données d'entrée et de sortie de l'API (validé par Pydantic)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EXEMPLE_EMPLOYE = {
    "age": 41,
    "genre": "F",
    "revenu_mensuel": 5993,
    "statut_marital": "Célibataire",
    "departement": "Commercial",
    "poste": "Cadre Commercial",
    "nombre_experiences_precedentes": 8,
    "annee_experience_totale": 8,
    "annees_dans_le_poste_actuel": 4,
    "nombre_participation_pee": 0,
    "nb_formations_suivies": 0,
    "distance_domicile_travail": 1,
    "niveau_education": 2,
    "domaine_etude": "Infra & Cloud",
    "frequence_deplacement": "Occasionnel",
    "annees_depuis_la_derniere_promotion": 0,
    "annes_sous_responsable_actuel": 5,
    "satisfaction_employee_environnement": 2,
    "note_evaluation_precedente": 3,
    "satisfaction_employee_nature_travail": 4,
    "satisfaction_employee_equipe": 1,
    "satisfaction_employee_equilibre_pro_perso": 1,
    "heure_supplementaires": "Oui",
    "augementation_salaire_precedente": 11,
}

Note = Field(ge=1, le=4)  # échelles de satisfaction et d'évaluation


class EmployeInput(BaseModel):
    """Profil d'un employé. Les noms de champs sont ceux des fichiers sources."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [EXEMPLE_EMPLOYE]})

    # Profil (SIRH)
    age: int = Field(ge=16, le=80, description="Âge en années")
    genre: Literal["F", "M"]
    revenu_mensuel: int = Field(gt=0, description="Revenu mensuel brut")
    statut_marital: Literal["Célibataire", "Marié(e)", "Divorcé(e)"]
    departement: Literal["Commercial", "Consulting", "Ressources Humaines"]
    poste: Literal[
        "Assistant de Direction",
        "Cadre Commercial",
        "Consultant",
        "Directeur Technique",
        "Manager",
        "Représentant Commercial",
        "Ressources Humaines",
        "Senior Manager",
        "Tech Lead",
    ]
    nombre_experiences_precedentes: int = Field(ge=0)
    annee_experience_totale: int = Field(ge=0, description="Années d'expérience au total")
    annees_dans_le_poste_actuel: int = Field(ge=0)

    # Sondage
    nombre_participation_pee: int = Field(ge=0, description="Participations au plan d'épargne")
    nb_formations_suivies: int = Field(ge=0)
    distance_domicile_travail: int = Field(ge=0, description="Distance en km")
    niveau_education: int = Field(ge=1, le=5)
    domaine_etude: Literal[
        "Autre",
        "Entrepreunariat",
        "Infra & Cloud",
        "Marketing",
        "Ressources Humaines",
        "Transformation Digitale",
    ]
    frequence_deplacement: Literal["Aucun", "Occasionnel", "Frequent"]
    annees_depuis_la_derniere_promotion: int = Field(ge=0)
    annes_sous_responsable_actuel: int = Field(ge=0, description="Années avec le manager actuel")

    # Évaluations
    satisfaction_employee_environnement: int = Note
    note_evaluation_precedente: int = Note
    satisfaction_employee_nature_travail: int = Note
    satisfaction_employee_equipe: int = Note
    satisfaction_employee_equilibre_pro_perso: int = Note
    heure_supplementaires: Literal["Oui", "Non"]
    augementation_salaire_precedente: int = Field(
        ge=0, le=100, description="Dernière augmentation, en % (ex. 11 pour 11 %)"
    )


class PredictionOutput(BaseModel):
    probabilite_depart: float = Field(ge=0, le=1, description="Probabilité de départ estimée")
    seuil: float = Field(description="Seuil de décision du modèle")
    depart_predit: bool = Field(description="True si probabilite_depart >= seuil")

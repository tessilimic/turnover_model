# Utiliser l'API

URL de base :

- en local : `http://localhost:7860`
- en ligne : `https://tessilimic-turnover-api.hf.space`
  (Space [tessilimic/turnover_api](https://huggingface.co/spaces/tessilimic/turnover_api) ;
  Hugging Face remplace `_` par `-` dans l'adresse directe)

| Méthode | Route | Rôle |
|---|---|---|
| `GET` | `/` | Redirige vers `/docs` |
| `GET` | `/health` | État du service |
| `POST` | `/predict` | Prédit le départ d'un employé et enregistre la prédiction |
| `GET` | `/docs` | Swagger UI (interface interactive) |
| `GET` | `/redoc` | Documentation ReDoc |
| `GET` | `/openapi.json` | Schéma OpenAPI (import Postman, génération de client) |

## Le plus simple : Swagger UI

1. Ouvrir `/docs`.
2. Déplier **POST /predict**, cliquer sur **Try it out**.
3. Le corps est pré-rempli avec un exemple valide : le modifier, puis **Execute**.

La réponse, le code HTTP et la commande `curl` équivalente s'affichent.

## Exemple de requête

```json
{
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
  "augementation_salaire_precedente": 11
}
```

Réponse (`200`) :

```json
{
  "id_prediction": 1471,
  "probabilite_depart": 0.6367,
  "seuil": 0.41,
  "depart_predit": true
}
```

| Champ | Signification |
|---|---|
| `id_prediction` | Identifiant de la prédiction dans la table `predictions` |
| `probabilite_depart` | Probabilité de départ estimée (0 à 1, arrondie à 4 décimales) |
| `seuil` | Seuil de décision du modèle |
| `depart_predit` | `true` si `probabilite_depart >= seuil` |

!!! info "Lire le résultat"
    Le seuil de 0,41 est volontairement bas pour **ne pas rater de départs** :
    environ 8 départs réels sur 10 sont signalés, mais seulement 3 alertes sur 10
    correspondent à un départ réel. Une alerte est un signal à examiner, pas une certitude.
    Voir [Performances](performances.md).

## Exemples de code

=== "curl (Linux / macOS)"

    ```bash
    curl -X POST http://localhost:7860/predict \
         -H "Content-Type: application/json" \
         --data-binary @employe.json
    ```

=== "PowerShell"

    ```powershell
    $body = Get-Content employe.json -Raw -Encoding UTF8
    Invoke-RestMethod -Uri http://localhost:7860/predict -Method Post `
        -ContentType "application/json; charset=utf-8" `
        -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
    ```

=== "Python"

    ```python
    import httpx

    employe = {"age": 41, "genre": "F", ...}  # les 24 champs

    reponse = httpx.post("http://localhost:7860/predict", json=employe)
    reponse.raise_for_status()
    resultat = reponse.json()
    print(f"Risque de départ : {resultat['probabilite_depart']:.0%}",
          "-> ALERTE" if resultat["depart_predit"] else "")
    ```

!!! warning "Accents et encodage"
    Le corps doit être envoyé en **UTF-8** (`Célibataire`, `Marié(e)`...).
    Sous Windows, un JSON tapé directement dans la ligne de commande part souvent
    dans un autre encodage, et l'API répond
    `There was an error parsing the body` : passer par un fichier, comme ci-dessus.

## Les 24 champs d'entrée

Tous les champs sont **obligatoires** ; un champ inconnu est refusé (protection contre
les fautes de frappe). Les noms reprennent ceux des fichiers sources, fautes comprises
(`augementation_salaire_precedente`, `annes_sous_responsable_actuel`).

| Champ | Type | Valeurs acceptées |
|---|---|---|
| `age` | entier | 16 à 80 |
| `genre` | texte | `F`, `M` |
| `revenu_mensuel` | entier | > 0 |
| `statut_marital` | texte | `Célibataire`, `Marié(e)`, `Divorcé(e)` |
| `departement` | texte | `Commercial`, `Consulting`, `Ressources Humaines` |
| `poste` | texte | `Assistant de Direction`, `Cadre Commercial`, `Consultant`, `Directeur Technique`, `Manager`, `Représentant Commercial`, `Ressources Humaines`, `Senior Manager`, `Tech Lead` |
| `nombre_experiences_precedentes` | entier | ≥ 0 |
| `annee_experience_totale` | entier | ≥ 0 (années) |
| `annees_dans_le_poste_actuel` | entier | ≥ 0 |
| `nombre_participation_pee` | entier | ≥ 0 (plan d'épargne entreprise) |
| `nb_formations_suivies` | entier | ≥ 0 |
| `distance_domicile_travail` | entier | ≥ 0 (km) |
| `niveau_education` | entier | 1 à 5 |
| `domaine_etude` | texte | `Autre`, `Entrepreunariat`, `Infra & Cloud`, `Marketing`, `Ressources Humaines`, `Transformation Digitale` |
| `frequence_deplacement` | texte | `Aucun`, `Occasionnel`, `Frequent` (sans accent) |
| `annees_depuis_la_derniere_promotion` | entier | ≥ 0 |
| `annes_sous_responsable_actuel` | entier | ≥ 0 (années avec le manager actuel) |
| `satisfaction_employee_environnement` | entier | 1 à 4 |
| `note_evaluation_precedente` | entier | 1 à 4 |
| `satisfaction_employee_nature_travail` | entier | 1 à 4 |
| `satisfaction_employee_equipe` | entier | 1 à 4 |
| `satisfaction_employee_equilibre_pro_perso` | entier | 1 à 4 |
| `heure_supplementaires` | texte | `Oui`, `Non` |
| `augementation_salaire_precedente` | entier | 0 à 100 (en %, ex. `11` pour 11 %) |

Les valeurs texte sont **sensibles à la casse et aux accents** : ce sont exactement
celles vues pendant l'entraînement.

## Erreurs

| Code | Cause | Enregistré en base ? |
|---|---|---|
| `422` | Champ manquant, valeur hors liste ou hors bornes, mauvais type, champ inconnu, JSON mal formé | Non |
| `405` | Mauvaise méthode (ex. `GET /predict`) | Non |
| `400` | Corps illisible (souvent un problème d'encodage) | Non |
| `500` | Erreur interne (base injoignable...) | Non |

Le détail d'une erreur `422` indique le champ en cause et les valeurs attendues :

```json
{
  "detail": [{
    "type": "literal_error",
    "loc": ["body", "poste"],
    "msg": "Input should be 'Assistant de Direction', 'Cadre Commercial', ...",
    "input": "Astronaute"
  }]
}
```

## Retrouver les prédictions

Chaque appel réussi crée une ligne dans `employes` (entrées) et une dans `predictions`
(résultat). Exemples de requêtes : `sql/02_requetes_utiles.sql`.

```bash
docker compose exec -T db psql -U turnover -d turnover < sql/02_requetes_utiles.sql
```

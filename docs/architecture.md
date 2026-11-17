# Architecture

## Vue d'ensemble

```mermaid
flowchart TB
    subgraph Dev["Poste du développeur"]
        CSV[(3 fichiers CSV<br/>data/)] -->|"src.db.init_db"| PG[(PostgreSQL<br/>Docker, port 5433)]
        PG -->|"src.train"| JOBLIB[model/pipeline.joblib<br/>+ metadata.json]
    end

    subgraph GH["GitHub"]
        REPO[Dépôt + Git LFS] --> CI["GitHub Actions<br/>ci.yaml : tests + build Docker + docs"]
        CI -->|"fusion dans main"| CD["deploy.yaml"]
    end

    subgraph HF["Hugging Face Spaces"]
        IMG["Image Docker<br/>FastAPI + modèle"] --> SQLITE[(SQLite<br/>non persistant)]
    end

    JOBLIB -->|"PR"| REPO
    CD -->|"git push (LFS)"| IMG
    USER[Utilisateur] -->|"HTTPS /predict"| IMG
```

## Composants

| Composant | Emplacement | Rôle |
|---|---|---|
| API | `app/main.py` | Routes FastAPI, démarrage (chargement du modèle, création des tables) |
| Schémas | `app/schemas.py` | Validation des entrées/sorties (Pydantic), exemple Swagger |
| Chargement du modèle | `app/model.py` | Lecture unique du `.joblib` (cache), `MODEL_PATH`, empreinte |
| Logs | `app/logs.py` | Logs JSON, `request_id` ajouté à chaque ligne |
| Traçabilité | `app/tracabilite.py` | Middleware (`X-Request-ID`, durée), journal `interactions`, `GET /logs` |
| Features | `src/features.py` | Listes de colonnes (source de vérité) et features créées |
| Entraînement | `src/train.py` | Lecture en base, pipeline, évaluation, export |
| Base de données | `src/db/` | Modèles ORM, connexion, chargement du jeu initial |
| SQL | `sql/` | Schéma PostgreSQL, réinitialisation, requêtes de consultation |
| Modèle | `model/` | Pipeline exporté (Git LFS) et métadonnées |
| Tests | `tests/{unit,integration,functional}/` | 3 catégories, voir [Tests](tests.md) |
| CI/CD | `.github/workflows/` | `ci.yaml` (tests, Docker, docs), `deploy.yaml` (Hugging Face) |
| Documentation | `docs/`, `mkdocs.yml`, `sphinx/` | Ce site (MkDocs) et la référence du code (Sphinx) |

## Flux d'une prédiction

```mermaid
sequenceDiagram
    actor C as Client
    participant API as FastAPI (/predict)
    participant P as Pydantic (EmployeInput)
    participant M as Pipeline scikit-learn
    participant DB as Base (employes, predictions)

    C->>API: POST /predict (JSON, 24 champs)
    API->>P: validation
    alt entrée invalide
        P-->>C: 422 + détail du champ (rien n'est enregistré)
    else entrée valide
        API->>M: predict_proba (1 ligne, colonnes dans l'ordre du modèle)
        M-->>API: probabilité
        API->>API: décision = probabilité >= seuil (0,41)
        API->>DB: INSERT employes + predictions (1 transaction)
        DB-->>API: id_prediction
        API-->>C: 200 {id_prediction, probabilite_depart, seuil, depart_predit}
    end
```

## Flux d'entraînement

```mermaid
flowchart LR
    A["3 CSV"] -->|"lire_csv() : fusion sur id_employee,<br/>nettoyage"| B["employes<br/>+ predictions (observation)"]
    B -->|"charger_donnees() :<br/>origine = 'observation' uniquement"| C["X (24 col.), y"]
    C -->|"80/20 stratifié"| D["Évaluation sur le test<br/>(métriques publiées)"]
    C -->|"100 %"| E["Modèle final"]
    E --> F["pipeline.joblib<br/>metadata.json"]
```

## Modèle de données

```mermaid
erDiagram
    employes ||--o{ predictions : "employe_id (ON DELETE CASCADE)"
    predictions |o--o{ interactions : "prediction_id (ON DELETE SET NULL)"
    interactions {
        int id PK
        varchar request_id UK "en-tête X-Request-ID"
        int code_http
        float duree_ms
        jsonb entrees "corps reçu, même invalide"
        jsonb erreurs "si 422"
        int prediction_id FK "NULL si refusée"
        varchar empreinte_modele
        timestamptz cree_le
    }
    employes {
        int id PK
        int id_employee UK "NULL si appel API"
        int age
        varchar genre
        int revenu_mensuel
        varchar poste
        string autres "… 24 colonnes d'entrée"
        timestamptz cree_le
    }
    predictions {
        int id PK
        int employe_id FK
        varchar origine "observation | prediction"
        bool depart
        float probabilite "NULL si observation"
        float seuil "NULL si observation"
        timestamptz cree_le
    }
```

Règles garanties **par la base** (contraintes) :

- une observation n'a ni probabilité ni seuil, une prédiction a les deux ;
- probabilité comprise entre 0 et 1 ;
- un seul départ observé par employé (index unique partiel) ;
- supprimer un employé supprime ses prédictions.

Le schéma PostgreSQL est défini dans `sql/01_schema.sql` ; les modèles ORM
(`src/db/models.py`) en sont le miroir, et un test vérifie que les colonnes coïncident.

## Environnements

| | Local (développement) | CI (GitHub Actions) | Production (Hugging Face) |
|---|---|---|---|
| Base | PostgreSQL 17 (Docker Compose) | PostgreSQL 17 (service) | SQLite dans le conteneur |
| Persistance | Volume Docker `pgdata` | Aucune (jetable) | Aucune (perdue au redémarrage) |
| Lancement | `docker compose up` | automatique (push, PR) | automatique (fusion dans `main`) |

## Arborescence

```text
turnover_model/
├── app/                  # API FastAPI
│   ├── main.py           #   routes /, /health, /predict
│   ├── schemas.py        #   entrées / sorties (Pydantic)
│   └── model.py          #   chargement du modèle
├── src/
│   ├── features.py       # colonnes + features créées
│   ├── train.py          # entraînement depuis la base, export
│   └── db/               # ORM, connexion, chargement des CSV
├── sql/                  # schéma PostgreSQL, reset, requêtes
├── model/                # pipeline.joblib (LFS) + metadata.json
├── data/                 # 3 CSV sources
├── notebooks/            # analyse exploratoire et modélisation
├── tests/                # unit / integration / functional
├── docs/  mkdocs.yml     # documentation MkDocs (ce site)
├── sphinx/               # référence du code (Sphinx)
├── scripts/              # export du schéma OpenAPI
├── .github/workflows/    # ci.yaml, deploy.yaml
├── Dockerfile  docker-compose.yml
└── requirements.txt  requirements-docs.txt
```

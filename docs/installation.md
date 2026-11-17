# Installation et configuration

## Prérequis

| Outil | Version | Usage |
|---|---|---|
| Python | 3.11 ou 3.12 (3.12 dans l'image Docker) | Entraînement, tests, documentation |
| Docker + Docker Compose | Docker 20.10+, Compose v2 | Base PostgreSQL locale, image de l'API |
| Git + Git LFS | Git LFS 3+ | Le modèle (`model/*.joblib`) est stocké avec Git LFS |

## 1. Récupérer le dépôt

```bash
git lfs install            # une seule fois par machine
git clone https://github.com/tessilimic/turnover_model.git
cd turnover_model
git lfs ls-files           # doit afficher : model/pipeline.joblib
```

!!! tip "Le modèle fait 3 lignes ?"
    Si `model/pipeline.joblib` ne fait que quelques octets, c'est le *pointeur* LFS :
    lancez `git lfs pull`.

## 2. Environnement Python

=== "Windows (PowerShell)"

    ```powershell
    python -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    ```

=== "Linux / macOS"

    ```bash
    python -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```

Pour construire la documentation, installer en plus `requirements-docs.txt`.

## 3. Base de données locale

```bash
docker compose up -d db        # PostgreSQL 17 sur localhost:5433
python -m src.db.init_db       # crée les tables et charge les 1 470 employés du jeu initial
```

`init_db` peut être relancé sans risque : il ne crée pas de doublon.
L'option `--reset` supprime les tables **et toutes les prédictions** avant de recharger.

## 4. Lancer l'API

=== "Avec Docker (recommandé)"

    ```bash
    docker compose up -d --build   # base + API
    ```

=== "Sans Docker (développement)"

    ```bash
    uvicorn app.main:app --reload --port 7860
    ```

Ouvrir <http://localhost:7860/docs> (Swagger UI).

## 5. Configuration

L'application se configure par **variables d'environnement** :

| Variable | Défaut | Rôle |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://turnover:turnover@localhost:5433/turnover` | Base utilisée par l'API, `init_db` et `train` |
| `MODEL_PATH` | `model/pipeline.joblib` | Modèle chargé par l'API |
| `TEST_DATABASE_URL` | *(vide : SQLite temporaire)* | Base utilisée par les tests |

Valeurs selon l'environnement :

| Environnement | `DATABASE_URL` |
|---|---|
| Local, hors Docker | défaut (PostgreSQL de `docker-compose.yml`) |
| `docker compose` | `postgresql+psycopg://turnover:turnover@db:5432/turnover` (fixé dans `docker-compose.yml`) |
| Image seule / Hugging Face | `sqlite:////home/user/db/turnover.db` (fixé dans le `Dockerfile`, non persistant) |

!!! note "Port 5433"
    La base Docker est exposée sur **5433** pour ne pas entrer en conflit avec un
    PostgreSQL déjà installé sur la machine (port 5432).

!!! danger "Identifiants"
    `turnover` / `turnover` sont des identifiants de **développement local**.
    Pour une base partagée ou hébergée, utiliser des identifiants forts, passés
    uniquement par `DATABASE_URL` (secret), jamais dans le code.

## 6. Vérifier l'installation

```bash
pytest -m unit                     # quelques secondes, sans base
pytest                             # tous les tests (SQLite temporaire)
curl http://localhost:7860/health  # {"status":"ok"}
```

## 7. Construire la documentation

```bash
pip install -r requirements-docs.txt
python -m scripts.export_openapi       # met à jour docs/api/openapi.json
mkdocs serve                           # aperçu sur http://127.0.0.1:8000

# Site complet (MkDocs + référence Sphinx dans site/code/) :
mkdocs build --strict
sphinx-build -W -b html sphinx site/code
```

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

## 3. Secrets (`.env`)

```bash
cp .env.example .env
```

Remplacer **chaque** valeur `a-remplacer` par une valeur aléatoire :

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

`.env` n'est jamais versionné (`.gitignore`). Il est lu par Docker Compose et par
l'application. Détail de chaque secret : [Sécurité](securite.md#secrets).

!!! warning "Base créée avant la version 1.0"
    Le mot de passe du compte propriétaire est fixé à la **création** du volume. Si une
    base existait déjà (anciens identifiants `turnover`/`turnover`), la recréer :
    `docker compose down -v` (supprime les données, rechargées à l'étape suivante).

## 4. Base de données locale

```bash
docker compose up -d db        # PostgreSQL 17 sur 127.0.0.1:5433
python -m src.db.init_db       # tables, rôles d'accès, jeu initial (1 470 employés)
```

`init_db` utilise la connexion administrateur (`ADMIN_DATABASE_URL`) et :

1. crée les tables (`sql/01_schema.sql`) ;
2. crée les rôles à privilèges minimaux `turnover_api`, `turnover_ml`,
   `turnover_auditeur` et leur attribue les mots de passe du `.env` (`sql/05_roles.sql`) ;
3. charge le jeu initial.

Il peut être relancé sans risque (pas de doublon ; utile après un changement de mot de
passe dans `.env`). `--reset` supprime les tables **et toutes les données** avant de recharger.

## 5. Créer les comptes de l'API

```bash
python -m app.utilisateurs creer admin --role admin       # mot de passe demandé sans écho
python -m app.utilisateurs creer marie.rh --role rh
python -m app.utilisateurs creer paul.audit --role auditeur
```

Rôles : `rh` (prédire), `auditeur` (consulter le journal), `admin` (tout).
Voir [Sécurité](securite.md#gerer-les-comptes).

## 6. Lancer l'API

=== "Avec Docker (recommandé)"

    ```bash
    docker compose up -d --build   # base + API, connectée avec le rôle turnover_api
    ```

=== "Sans Docker (développement)"

    ```bash
    uvicorn app.main:app --reload --port 7860   # lit DATABASE_URL et JWT_SECRET dans .env
    ```

Ouvrir <http://127.0.0.1:7860/docs>, bouton **Authorize**, se connecter.

## 7. Configuration

| Variable | Utilisée par | Rôle |
|---|---|---|
| `DATABASE_URL` | API | Connexion avec le rôle `turnover_api` |
| `ML_DATABASE_URL` | `src.train` | Connexion avec le rôle `turnover_ml` (lecture seule) |
| `ADMIN_DATABASE_URL` | `init_db`, `app.utilisateurs` | Connexion propriétaire |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Docker Compose | Compte propriétaire de la base |
| `TURNOVER_API_DB_PASSWORD`, `TURNOVER_ML_DB_PASSWORD`, `TURNOVER_AUDITEUR_DB_PASSWORD` | `init_db`, Docker Compose | Mots de passe des rôles |
| `JWT_SECRET` | API | Signature des jetons (≥ 32 caractères) |
| `JWT_DUREE_MINUTES` | API | Durée de validité d'un jeton (30 par défaut) |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | API sur SQLite | Compte admin créé au démarrage (Hugging Face) |
| `MODEL_PATH` | API | Modèle chargé (`model/pipeline.joblib` par défaut) |
| `LOG_LEVEL`, `LOG_FILE` | API | Logs techniques (voir [Logs](logs.md)) |
| `TEST_DATABASE_URL`, `TEST_ROLES_PG` | tests | Voir [Tests](tests.md) |

Il n'y a **aucune valeur par défaut** pour les connexions : sans `.env` ni variable,
les commandes s'arrêtent avec un message explicite. Si `ML_DATABASE_URL` ou
`ADMIN_DATABASE_URL` est absent, `DATABASE_URL` est utilisé.

| Environnement | Base |
|---|---|
| Local, hors Docker | PostgreSQL de `docker-compose.yml`, via `.env` |
| `docker compose` | Rôle `turnover_api`, adresse construite dans `docker-compose.yml` |
| Image seule / Hugging Face | `sqlite:////home/user/db/turnover.db` (`Dockerfile`, non persistant) |

!!! note "Port 5433 et 127.0.0.1"
    La base Docker est exposée sur **5433** (pas de conflit avec un PostgreSQL déjà
    installé) et seulement sur **127.0.0.1** (pas d'accès depuis le réseau). Utiliser
    `127.0.0.1` plutôt que `localhost` dans les adresses : sous Windows, `localhost`
    est d'abord résolu en IPv6 (`::1`), où la base n'écoute pas.

## 8. Vérifier l'installation

```bash
pytest -m unit                     # quelques secondes, sans base
pytest                             # tous les tests (SQLite temporaire)
curl http://127.0.0.1:7860/health  # {"status":"ok"}
```

## 9. Construire la documentation

```bash
pip install -r requirements-docs.txt
python -m scripts.export_openapi       # met à jour docs/api/openapi.json
mkdocs serve                           # aperçu sur http://127.0.0.1:8000

# Site complet (MkDocs + référence Sphinx dans site/code/) :
mkdocs build --strict
sphinx-build -W -b html sphinx site/code
```

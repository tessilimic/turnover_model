---
title: Turnover API
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

<a id="readme-top"></a>

<!-- PROJECT SHIELDS -->
[![CI][ci-shield]][ci-url]
[![Python][python-shield]][python-url]
[![FastAPI][fastapi-shield]][fastapi-url]
[![scikit-learn][sklearn-shield]][sklearn-url]
[![PostgreSQL][postgres-shield]][postgres-url]
[![Docker][docker-shield]][docker-url]
[![Hugging Face][hf-shield]][hf-url]

<!-- PROJECT LOGO -->
<br />
<div align="center">
  <h3 align="center">Turnover API</h3>

  <p align="center">
    Prédiction du risque de départ des employés : un modèle de Machine Learning exposé par une API REST, déployé en continu.
    <br />
    <a href="docs/index.md"><strong>Explorer la documentation »</strong></a>
    <br />
    <br />
    <a href="#usage">Exemples</a>
    &middot;
    <a href="docs/api/index.md">Référence de l'API</a>
    &middot;
    <a href="https://github.com/tessilimic/turnover_model/issues/new?labels=bug">Signaler un bug</a>
    &middot;
    <a href="https://github.com/tessilimic/turnover_model/issues/new?labels=enhancement">Proposer une évolution</a>
  </p>
</div>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Sommaire</summary>
  <ol>
    <li>
      <a href="#about-the-project">À propos du projet</a>
      <ul>
        <li><a href="#built-with">Technologies</a></li>
        <li><a href="#architecture">Architecture</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Démarrage</a>
      <ul>
        <li><a href="#prerequisites">Prérequis</a></li>
        <li><a href="#installation">Installation</a></li>
        <li><a href="#configuration">Configuration</a></li>
      </ul>
    </li>
    <li><a href="#usage">Utilisation</a></li>
    <li><a href="#the-model">Le modèle</a></li>
    <li><a href="#deployment">Déploiement</a></li>
    <li><a href="#documentation">Documentation</a></li>
    <li><a href="#roadmap">Feuille de route</a></li>
    <li><a href="#contributing">Contribuer</a></li>
    <li><a href="#license">Licence</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Remerciements</a></li>
  </ol>
</details>

<!-- ABOUT THE PROJECT -->
<a id="about-the-project"></a>

## À propos du projet

À partir du profil RH d'un employé (SIRH, sondage interne, évaluations), un modèle
**Random Forest** estime la probabilité qu'il quitte l'entreprise. L'API renvoie cette
probabilité et une décision, et **enregistre chaque prédiction** en base de données.

* **Objectif** : aider les RH à cibler les actions de rétention, en détectant un maximum
  de départs (81 % des départs détectés sur le jeu de test).
* **Industrialisé** : pipeline complet exporté, API validée, base de données, 140 tests,
  CI/CD jusqu'au déploiement sur Hugging Face Spaces.
* **Documenté** : Swagger, site MkDocs, référence du code Sphinx, protocole de maintenance.

> [!WARNING]
> Outil d'**aide à la décision** : environ 7 alertes sur 10 sont des fausses alertes.
> Il ne doit pas fonder seul une décision concernant un employé
> (voir [les limites du modèle](docs/modele.md#limites-et-precautions)).

<p align="right">(<a href="#readme-top">retour en haut</a>)</p>

<a id="built-with"></a>

### Technologies

| Domaine | Outils |
|---|---|
| Modèle | [![scikit-learn][sklearn-shield]][sklearn-url] pandas, NumPy, joblib |
| API | [![FastAPI][fastapi-shield]][fastapi-url] Pydantic, Uvicorn |
| Données | [![PostgreSQL][postgres-shield]][postgres-url] SQLAlchemy (ORM), psycopg, SQLite |
| Déploiement | [![Docker][docker-shield]][docker-url] [![Hugging Face][hf-shield]][hf-url] GitHub Actions, Git LFS |
| Qualité | pytest, pytest-cov, Dependabot |
| Documentation | Swagger (OpenAPI), Markdown, MkDocs Material, Sphinx |

Les raisons de chaque choix sont détaillées dans [Choix techniques](docs/choix-techniques.md).

<a id="architecture"></a>

### Architecture

```mermaid
flowchart LR
    CSV[(3 CSV)] -->|init_db| PG[(PostgreSQL)]
    PG -->|train| M[pipeline.joblib]
    M --> API[API FastAPI]
    U[Client] -->|POST /predict| API
    API -->|employes + predictions| PG
    API -->|probabilité, décision| U
```

| Dossier | Contenu |
|---|---|
| `app/` | API FastAPI : routes, schémas Pydantic, chargement du modèle |
| `src/` | Features, entraînement, base de données (ORM) |
| `sql/` | Schéma PostgreSQL et requêtes de suivi |
| `model/` | Modèle exporté (Git LFS) et métadonnées |
| `tests/` | Tests unitaires, d'intégration et fonctionnels |
| `docs/`, `sphinx/` | Documentation MkDocs et référence du code |

Détails : [Architecture](docs/architecture.md).

<p align="right">(<a href="#readme-top">retour en haut</a>)</p>

<!-- GETTING STARTED -->
<a id="getting-started"></a>

## Démarrage

<a id="prerequisites"></a>

### Prérequis

* Python 3.11 ou 3.12
* Docker et Docker Compose v2
* Git LFS
  ```sh
  git lfs install
  ```

<a id="installation"></a>

### Installation

1. Cloner le dépôt (le modèle est récupéré par Git LFS)
   ```sh
   git clone https://github.com/tessilimic/turnover_model.git
   cd turnover_model
   ```
2. Installer les dépendances
   ```sh
   python -m venv .venv
   source .venv/bin/activate      # Windows : .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
3. Démarrer PostgreSQL et charger le jeu de données
   ```sh
   docker compose up -d db
   python -m src.db.init_db
   ```
4. (Optionnel) Réentraîner le modèle depuis la base
   ```sh
   python -m src.train
   ```
5. Lancer l'API, puis ouvrir http://localhost:7860/docs
   ```sh
   docker compose up -d --build
   ```
6. Vérifier
   ```sh
   pytest
   ```

<a id="configuration"></a>

### Configuration

| Variable | Défaut | Rôle |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://turnover:turnover@localhost:5433/turnover` | Base de données (API, `init_db`, `train`) |
| `MODEL_PATH` | `model/pipeline.joblib` | Modèle chargé par l'API |
| `TEST_DATABASE_URL` | SQLite temporaire | Base utilisée par les tests |

Guide complet : [Installation et configuration](docs/installation.md).

<p align="right">(<a href="#readme-top">retour en haut</a>)</p>

<!-- USAGE EXAMPLES -->
<a id="usage"></a>

## Utilisation

Le plus simple : **Swagger UI** sur `/docs`, bouton *Try it out* (exemple pré-rempli).

```sh
curl -X POST http://localhost:7860/predict \
     -H "Content-Type: application/json" \
     --data-binary @employe.json
```

```json
{"id_prediction": 1471, "probabilite_depart": 0.6367, "seuil": 0.41, "depart_predit": true}
```

En Python :

```python
import httpx

reponse = httpx.post("http://localhost:7860/predict", json=employe)  # 24 champs
print(reponse.json()["probabilite_depart"])
```

| Route | Rôle |
|---|---|
| `POST /predict` | Prédit et enregistre (24 champs obligatoires, validés) |
| `GET /health` | État du service |
| `GET /docs`, `/redoc` | Documentation interactive |

Les 24 champs, leurs valeurs acceptées et les erreurs : [Utiliser l'API](docs/utilisation.md).

<p align="right">(<a href="#readme-top">retour en haut</a>)</p>

<!-- THE MODEL -->
<a id="the-model"></a>

## Le modèle

| | |
|---|---|
| Algorithme | Random Forest, 300 arbres, profondeur 4, pondération des classes |
| Données | 1 470 employés, 16 % de départs, 24 colonnes + 7 features créées |
| Seuil | 0,41 (maximise le F2 : rater un départ coûte plus qu'une fausse alerte) |
| Test | ROC AUC **0,769** · recall **0,81** · precision **0,29** |

Fiche complète : [Fiche technique](docs/modele.md) et [Performances](docs/performances.md).

<p align="right">(<a href="#readme-top">retour en haut</a>)</p>

<!-- DEPLOYMENT -->
<a id="deployment"></a>

## Déploiement

```mermaid
flowchart LR
    B[Branche] --> PR[Pull Request] --> CI["CI : tests, Docker, docs"] -->|verte| M[main] --> D[deploy.yaml] --> HF[Hugging Face Space]
```

* **CI** (`.github/workflows/ci.yaml`) : tests unitaires, d'intégration (PostgreSQL) et
  fonctionnels, build de l'image Docker, build de la documentation.
* **CD** (`.github/workflows/deploy.yaml`) : à chaque fusion dans `main`, relance la CI
  puis pousse le code vers le Space, qui reconstruit l'image.
* **Configuration GitHub** : secret `HF_TOKEN`, variables `HF_USERNAME` et `HF_SPACE_NAME`.

Détails, vérification et retour arrière : [Déploiement](docs/deploiement.md).

<p align="right">(<a href="#readme-top">retour en haut</a>)</p>

<!-- DOCUMENTATION -->
<a id="documentation"></a>

## Documentation

| Outil | Contenu | Accès |
|---|---|---|
| **Swagger** | Référence interactive de l'API | `/docs` sur l'API, [docs/api](docs/api/index.md) |
| **MkDocs** | Guides, modèle, architecture, maintenance | `mkdocs serve` |
| **Sphinx** | Référence du code (docstrings) | `sphinx-build -b html sphinx site/code` |
| **Markdown** | Ce README et les pages de `docs/` | Directement sur GitHub |

```sh
pip install -r requirements-docs.txt
mkdocs serve                                   # http://127.0.0.1:8000
```

Le site complet est aussi produit par la CI (artefact *documentation*).

<p align="right">(<a href="#readme-top">retour en haut</a>)</p>

<!-- ROADMAP -->
<a id="roadmap"></a>

## Feuille de route

- [x] Pipeline CI/CD et déploiement sur Hugging Face Spaces
- [x] API FastAPI avec validation et Swagger
- [x] Base PostgreSQL, enregistrement des prédictions
- [x] Tests unitaires, d'intégration et fonctionnels
- [x] Documentation et protocole de maintenance
- [ ] Import incrémental des nouveaux départs observés
- [ ] Réévaluation de la régression logistique ; modèle sans variables sensibles
- [ ] Explication SHAP de chaque prédiction
- [ ] Base PostgreSQL hébergée, authentification de l'API

Protocole de mise à jour régulière : [Maintenance](docs/maintenance.md).

<p align="right">(<a href="#readme-top">retour en haut</a>)</p>

<!-- CONTRIBUTING -->
<a id="contributing"></a>

## Contribuer

1. Créer une branche (`git switch -c feature/ma-modification`)
2. Ajouter des tests dans `tests/unit`, `tests/integration` ou `tests/functional`
3. Vérifier en local (`pytest`)
4. Pousser la branche (`git push -u origin feature/ma-modification`)
5. Ouvrir une Pull Request : la CI doit être verte avant la fusion

Liste de contrôle et conventions : [Contribuer](docs/contribuer.md).

<p align="right">(<a href="#readme-top">retour en haut</a>)</p>

<!-- LICENSE -->
<a id="license"></a>

## Licence

Aucune licence n'est définie pour l'instant : tous droits réservés.

<p align="right">(<a href="#readme-top">retour en haut</a>)</p>

<!-- CONTACT -->
<a id="contact"></a>

## Contact

Projet : [github.com/tessilimic/turnover_model](https://github.com/tessilimic/turnover_model)
— questions et anomalies via les [issues](https://github.com/tessilimic/turnover_model/issues).

<p align="right">(<a href="#readme-top">retour en haut</a>)</p>

<!-- ACKNOWLEDGMENTS -->
<a id="acknowledgments"></a>

## Remerciements

* [OpenClassrooms](https://openclassrooms.com/) — parcours et sujet du projet
* [Best-README-Template](https://github.com/othneildrew/Best-README-Template) — structure de ce README
* [Shields.io](https://shields.io) — badges
* [FastAPI](https://fastapi.tiangolo.com/), [scikit-learn](https://scikit-learn.org/),
  [SQLAlchemy](https://www.sqlalchemy.org/), [MkDocs Material](https://squidfunk.github.io/mkdocs-material/),
  [Sphinx](https://www.sphinx-doc.org/)

<p align="right">(<a href="#readme-top">retour en haut</a>)</p>

<!-- MARKDOWN LINKS & IMAGES -->
[ci-shield]: https://github.com/tessilimic/turnover_model/actions/workflows/ci.yaml/badge.svg
[ci-url]: https://github.com/tessilimic/turnover_model/actions/workflows/ci.yaml
[python-shield]: https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white
[python-url]: https://www.python.org/
[fastapi-shield]: https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white
[fastapi-url]: https://fastapi.tiangolo.com/
[sklearn-shield]: https://img.shields.io/badge/scikit--learn-1.9.1-F7931E?logo=scikitlearn&logoColor=white
[sklearn-url]: https://scikit-learn.org/
[postgres-shield]: https://img.shields.io/badge/PostgreSQL-17-4169E1?logo=postgresql&logoColor=white
[postgres-url]: https://www.postgresql.org/
[docker-shield]: https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white
[docker-url]: https://www.docker.com/
[hf-shield]: https://img.shields.io/badge/Hugging%20Face-Space-FFD21E?logo=huggingface&logoColor=black
[hf-url]: https://huggingface.co/spaces/HF_USERNAME/turnover-api

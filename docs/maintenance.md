# Maintenance et mises à jour

Un modèle de Machine Learning se dégrade **sans erreur visible** : l'API continue de
répondre, mais les prédictions deviennent moins fiables à mesure que l'entreprise
évolue. Ce protocole organise la surveillance et les mises à jour.

## Calendrier

| Fréquence | Action | Responsable | Durée |
|---|---|---|---|
| **Continue** | CI sur chaque PR (tests, Docker, documentation) | Automatique | — |
| **Hebdomadaire** | Revue des PR Dependabot (dépendances, actions, image Docker) | Développeur | 15 min |
| **Mensuelle** | [Suivi des prédictions](#suivi-mensuel) (`sql/03_suivi.sql`) | Data scientist | 30 min |
| **Trimestrielle** | [Réentraînement](#reentrainement) avec les nouveaux départs observés | Data scientist | 1/2 journée |
| **Annuelle** | [Revue complète](#revue-annuelle) : notebook, hyperparamètres, seuil, équité | Data scientist + RH | 2-3 jours |
| **Sur événement** | Voir [déclencheurs](#declencheurs-hors-calendrier) | Selon le cas | — |

## Suivi mensuel

```bash
docker compose exec -T db psql -U turnover -d turnover < sql/03_suivi.sql
```

| Indicateur | Valeur de référence | Alerte si |
|---|---|---|
| Probabilité moyenne prédite | 0,42 (jeu d'entraînement ; élevée car le modèle est pondéré) | Écart > 0,10 sur un mois |
| Part de départs prédits | 43 % (jeu d'entraînement) | < 30 % ou > 60 % |
| Profil des employés évalués (âge, revenu, heures sup.) | Requête 3 de `03_suivi.sql` | Écart marqué avec l'entraînement |
| Volume d'appels | — | Chute brutale (API indisponible ?) |
| Départs réels vs prédits (quand connus) | Recall ≈ 0,8 | Recall < 0,7 |

Une alerte déclenche un **réentraînement anticipé** et une analyse des données récentes
(nouveau poste, nouvelle politique salariale...).

## Réentraînement

### 1. Mettre à jour les données

Les nouveaux départs observés sont ajoutés dans la base comme **observations**
(`predictions.origine = 'observation'`), rattachées à leur ligne `employes`.

!!! note "Pas encore outillé"
    L'import de nouvelles observations n'a pas de script dédié : aujourd'hui, mettre à
    jour les 3 CSV puis `python -m src.db.init_db --reset` (attention : supprime aussi
    les prédictions). Un script d'import incrémental figure dans la
    [feuille de route](#feuille-de-route).

### 2. Entraîner et comparer

```bash
git switch -c model/retrain-AAAA-MM
python -m src.train
git diff model/metadata.json          # comparer les métriques avec la version précédente
pytest
```

### 3. Critères d'acceptation { #criteres-dacceptation }

Le nouveau modèle n'est fusionné que si, sur le jeu de test :

| Critère | Seuil minimal | Modèle actuel |
|---|---|---|
| ROC AUC | ≥ 0,75 **et** pas plus de 0,02 sous le modèle actuel | 0,769 |
| Recall au seuil | ≥ 0,75 | 0,809 |
| Precision au seuil | ≥ 0,25 | 0,292 |
| Tous les tests | verts | — |

Si le test `test_entrainement_reproduit_le_notebook` échoue parce que les **données** ont
changé (et non le code), mettre à jour ses valeurs attendues dans la même PR, en
justifiant l'écart dans la description.

### 4. Publier

1. Commiter `model/pipeline.joblib` (LFS) et `model/metadata.json`.
2. Incrémenter `version` dans `app/main.py`, puis `python -m scripts.export_openapi`.
3. PR décrivant les données utilisées et les métriques avant/après → CI → fusion → déploiement.
4. [Vérifier le déploiement](deploiement.md#verifier-un-deploiement).

## Revue annuelle

- Relancer le notebook sur les données à jour : la recherche d'hyperparamètres et le
  seuil (F2) sont-ils toujours optimaux ?
- Comparer avec d'autres algorithmes, en priorité la **régression logistique** (meilleur
  ROC AUC de référence) et un gradient boosting.
- **Équité** : comparer recall et precision par `genre` et `statut_marital` ; décider
  avec les RH et le DPO du maintien de ces variables.
- Mettre à jour la [fiche du modèle](modele.md) et les [performances](performances.md).

## Déclencheurs hors calendrier

| Événement | Action |
|---|---|
| Nouveau poste, département ou domaine d'études | Réentraîner avec des exemples ; mettre à jour les `Literal` de `app/schemas.py` (un test signale l'écart) |
| Alerte du suivi mensuel | Réentraînement anticipé + analyse |
| Faille de sécurité dans une dépendance | PR Dependabot à traiter sous 7 jours |
| Nouvelle version de scikit-learn | Voir ci-dessous |
| Réorganisation, changement de politique RH | Revue complète |

## Mettre à jour les dépendances

[Dependabot](https://docs.github.com/fr/code-security/dependabot) ouvre chaque semaine
des PR pour les paquets Python, les actions GitHub et l'image Docker
(`.github/dependabot.yml`). La CI les teste automatiquement.

| Paquet | Procédure |
|---|---|
| FastAPI, uvicorn, SQLAlchemy, psycopg, pytest... | Fusionner si la CI est verte |
| **scikit-learn, numpy, pandas, joblib** | La CI échoue volontairement (`test_version_scikit_learn_identique`) : dans la même PR, **réentraîner** le modèle avec la nouvelle version, vérifier les critères d'acceptation, commiter le `.joblib` |
| Python (image Docker, CI) | Mettre à jour `Dockerfile` et `ci.yaml` ensemble |
| PostgreSQL | Mettre à jour `docker-compose.yml` et `ci.yaml` ensemble |

## Maintenir la documentation

| Changement | Mise à jour |
|---|---|
| Route, schéma ou description de l'API | `python -m scripts.export_openapi` (sinon `test_openapi_a_jour` échoue) |
| Nouveau modèle | `modele.md`, `performances.md`, tableau « En bref » de l'accueil, README |
| Nouvelle fonction ou module | Docstring au format Google ; l'ajouter dans `sphinx/*.rst` si nouveau module |
| Installation, configuration | `installation.md` et section *Getting Started* du README |

La CI construit MkDocs (`--strict`) et Sphinx (`-W`) : un lien cassé, une page absente du
menu ou une docstring invalide bloque la PR.

## Feuille de route

- [ ] Script d'import incrémental des nouveaux départs observés.
- [ ] Réévaluer la régression logistique réglée dans les mêmes conditions que la forêt.
- [ ] Étudier un modèle sans `genre` ni `statut_marital` (équité).
- [ ] Explication de chaque prédiction dans l'API (valeurs SHAP).
- [ ] Base PostgreSQL hébergée pour conserver les prédictions de production.
- [ ] Migrations de schéma (Alembic) dès que la base de production contient des données.
- [ ] Authentification de l'API (clé d'API) avant tout usage avec des données réelles.
- [ ] Publication de la documentation sur GitHub Pages.

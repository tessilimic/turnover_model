# Tests

## Organisation

| Dossier | Marqueur | Ce qui est testé | Dépendances |
|---|---|---|---|
| `tests/unit/` | `unit` | Une fonction isolée : schémas, features, logique de `/predict` (faux modèle, fausse session), fusion des CSV (petits fichiers temporaires), configuration | Aucune |
| `tests/integration/` | `integration` | La vraie base (schéma, contraintes, chargement) et le vrai modèle (reproduction du notebook, cohérence avec l'API) | Base de données, `pipeline.joblib` |
| `tests/functional/` | `functional` | L'API appelée en HTTP, de bout en bout, enregistrement en base compris | Base de données, `pipeline.joblib` |

Le marqueur est ajouté **automatiquement** selon le dossier (`tests/conftest.py`). Un test
placé ailleurs fait échouer pytest.

## Lancer les tests

```bash
pytest                    # tout, sur une base SQLite temporaire
pytest -m unit            # unitaires seuls (quelques secondes, sans base)
pytest -m "not functional"
pytest --cov --cov-report=term-missing
```

Sur PostgreSQL, comme en CI :

```bash
docker compose up -d db
docker compose exec db createdb -U turnover turnover_test     # une seule fois
TEST_DATABASE_URL=postgresql+psycopg://turnover:turnover@localhost:5433/turnover_test pytest
```

!!! danger "Base de développement protégée"
    `tests/conftest.py` remplace `DATABASE_URL` **avant** tout import de l'application :
    les tests ne peuvent pas toucher la base de développement, même si la variable est
    définie dans votre terminal. La base de test est vidée au début de chaque session.

## Garde-fous notables

| Test | Protège contre |
|---|---|
| `test_entrainement_reproduit_le_notebook` | Une régression de l'entraînement (ROC AUC 0,769) |
| `test_version_scikit_learn_identique` | Un modèle exporté avec une autre version de scikit-learn |
| `test_modalites_du_schema_identiques_a_celles_apprises` | Un écart entre les valeurs acceptées par l'API et celles du modèle |
| `test_colonnes_en_base_identiques_a_l_orm` | Un écart entre `sql/01_schema.sql` et les modèles ORM |
| `test_donnees_en_base_identiques_aux_csv` | Une différence entre l'entraînement depuis la base et depuis les CSV |
| `test_openapi_a_jour` | Une documentation Swagger (export) périmée |
| `test_predictions_api_exclues_de_l_entrainement` | L'apprentissage sur les prédictions du modèle lui-même |

## Écrire un nouveau test

- Choisir le dossier selon ce que le test **utilise** (pas selon ce qu'il teste) :
  sans base ni `.joblib` → `unit/`.
- Fixtures disponibles : `engine` (base de test chargée, partagée par la session).
- Pour `/predict` sans dépendances : voir `tests/unit/test_predict.py`
  (`app.dependency_overrides`).
- Structure *Arrange / Act / Assert*, noms en français décrivant le comportement attendu.

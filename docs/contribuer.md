# Contribuer

## Flux de travail

Toute modification passe par une **branche** et une **Pull Request** ; `main` n'est
jamais modifiée directement (chaque fusion déclenche un déploiement).

```bash
git switch main && git pull
git switch -c feature/ma-modification     # feature/, fix/, model/, docs/
# ... modifications + tests ...
pytest
git push -u origin feature/ma-modification
```

Puis ouvrir la PR sur GitHub : la CI doit être verte avant la fusion.

## Liste de contrôle d'une PR

- [ ] Tests ajoutés ou mis à jour, dans le bon dossier (`unit`, `integration`, `functional`).
- [ ] `pytest` vert en local.
- [ ] API modifiée → `python -m scripts.export_openapi`.
- [ ] Nouvelle dépendance → `requirements.txt` (version figée si elle touche le modèle).
- [ ] Schéma de base modifié → `sql/01_schema.sql` **et** `src/db/models.py`.
- [ ] Modèle réentraîné → `pipeline.joblib` + `metadata.json`, métriques dans la description.
- [ ] Documentation à jour (voir [Maintenance](maintenance.md#maintenir-la-documentation)).

## Conventions

| Sujet | Convention |
|---|---|
| Langue | Code, docstrings, tests et documentation en français ; commentaires techniques des fichiers d'infrastructure en anglais |
| Docstrings | Format Google (`Args`, `Returns`, `Raises`), lues par Sphinx |
| Noms de colonnes | Identiques aux fichiers sources (fautes comprises) |
| Commits | Préfixe `[turnover]`, message à l'impératif |

## Documentation

```bash
pip install -r requirements-docs.txt
mkdocs serve                              # aperçu en direct
mkdocs build --strict && sphinx-build -W -b html sphinx site/code
```

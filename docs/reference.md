# Référence du code (Sphinx)

La référence de chaque module, classe et fonction est générée par **Sphinx** (autodoc)
à partir des docstrings du code.

<p><a class="md-button md-button--primary" href="../code/">Ouvrir la référence du code</a></p>

| Section | Modules |
|---|---|
| API | `app.main`, `app.schemas`, `app.model` |
| Modèle | `src.features`, `src.train` |
| Base de données | `src.db.models`, `src.db.session`, `src.db.init_db` |
| Scripts | `scripts.export_openapi` |

En ligne : <https://tessilimic.github.io/turnover_model/code/> (publiée sur GitHub Pages
à chaque fusion dans `main`).

!!! note "En local"
    La référence est construite avec le site complet (`site/code/`) :

    ```bash
    mkdocs build --strict
    sphinx-build -W -b html sphinx site/code
    ```

    Avec `mkdocs serve` (aperçu), le lien ci-dessus ne fonctionne pas : ouvrir
    `site/code/index.html` après la construction complète, ou télécharger l'artefact
    *documentation* d'une exécution de la CI.

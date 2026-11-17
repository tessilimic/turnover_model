# Déploiement (CI/CD)

```mermaid
flowchart LR
    B[Branche feature/...] --> PR[Pull Request]
    PR --> CI["CI (ci.yaml)<br/>tests unit · intégration · fonctionnels<br/>build Docker · build docs"]
    CI -->|"verte"| M[Fusion dans main]
    M --> D["deploy.yaml<br/>relance la CI puis git push"]
    D --> HF["Hugging Face Space<br/>reconstruit l'image et redémarre"]
```

## Workflows GitHub Actions

### `ci.yaml` : intégration continue

Déclenché à chaque push et chaque PR, et réutilisé par `deploy.yaml`.

| Job | Étapes |
|---|---|
| **Tests** | Service PostgreSQL 17 ; tests unitaires, puis d'intégration, puis fonctionnels (couverture cumulée) |
| **Docker build** | Construit l'image (après les tests) |
| **Documentation** | Vérifie l'export OpenAPI, `mkdocs build --strict`, `sphinx-build -W` ; publie le site en artefact |

Les fichiers LFS sont récupérés (`lfs: true`) : sans cela, les tests liraient un
pointeur au lieu du modèle.

### `deploy.yaml` : déploiement continu

Déclenché à chaque push sur `main` (donc à chaque fusion de PR), ou manuellement
(onglet Actions, *Run workflow*).

1. Relance toute la CI ; rien n'est déployé si elle échoue.
2. Puis, en parallèle :
    - **API** : vérifie `HF_TOKEN`, `HF_USERNAME`, `HF_SPACE_NAME`, puis `git push --force`
      vers le dépôt du Space (fichiers LFS inclus) ;
    - **Documentation** : construit MkDocs et Sphinx, puis publie le site sur
      **GitHub Pages** : <https://tessilimic.github.io/turnover_model/>
      (référence du code dans [`/code/`](https://tessilimic.github.io/turnover_model/code/)).

Les deux publications sont indépendantes : un échec du Space ne bloque pas la
documentation. Deux déploiements ne se chevauchent jamais (le second attend le premier).

## Configuration

### GitHub (*Settings → Secrets and variables → Actions*)

| Nom | Type | Valeur |
|---|---|---|
| `HF_TOKEN` | Secret | Jeton Hugging Face *fine-grained*, écriture sur le Space uniquement |
| `HF_USERNAME` | Variable | Identifiant Hugging Face : `tessilimic` |
| `HF_SPACE_NAME` | Variable | Nom du Space : `turnover_api` |

### GitHub Pages

Une seule fois : *Settings → Pages → Build and deployment → Source* : **GitHub Actions**.
Gratuit pour un dépôt public (un dépôt privé nécessite un abonnement GitHub payant) ;
le site est alors public.

### Protection de `main`

Recommandé : protéger `main` (*Settings → Branches*) en exigeant une PR et les
vérifications **Tests (pytest)**, **Docker build** et **Documentation**.

### Hugging Face Space

- SDK **Docker**, matériel **CPU basic** (gratuit).
- L'en-tête du `README.md` (`sdk: docker`, `app_port: 7860`) configure le Space.
- L'application écoute sur `0.0.0.0:7860` avec l'utilisateur UID 1000 (`Dockerfile`).
- Logs : onglet **Logs** du Space. Pour activer `GET /logs`, ajouter un secret
  `LOGS_API_KEY` (clé longue et aléatoire) dans *Settings → Variables and secrets*.
- Base : SQLite non persistante par défaut. Pour une base persistante, ajouter un secret
  `DATABASE_URL` dans *Settings → Variables and secrets* du Space (PostgreSQL hébergé).

## Vérifier un déploiement

1. Onglet **Actions** : le workflow *Deploy (Hugging Face Spaces + GitHub Pages)* est vert.
2. Onglet **Files** du Space : `model/pipeline.joblib` porte le badge **LFS**.
3. Onglet **Logs** du Space : `Application startup complete`.
4. `GET /health` renvoie `{"status": "ok"}` ; `/docs` affiche Swagger.

## Revenir en arrière

Un déploiement défectueux se corrige par une nouvelle PR, jamais par un push direct :

```bash
git switch -c fix/revert-xxx
git revert -m 1 <commit de fusion fautif>
git push -u origin fix/revert-xxx      # puis PR -> CI -> fusion -> redéploiement
```

En urgence, le workflow peut être relancé manuellement sur un état antérieur de `main`
après le revert.

## Problèmes connus

| Symptôme | Cause | Solution |
|---|---|---|
| Push refusé `403` | Mauvais compte GitHub mémorisé | `git config --local credential.https://github.com.username <compte>` |
| `You must have push access to verify locks` | Git LFS ancien n'envoie pas les identifiants | `git config --local "lfs.<url du dépôt>/info/lfs.access" basic` |
| Push vers le Space refusé (fichier binaire) | Fichier binaire hors LFS | Vérifier `.gitattributes` et `git lfs ls-files` |
| Space en erreur au démarrage | Modèle absent (pointeur LFS) ou version de scikit-learn différente | Logs du Space ; voir [Maintenance](maintenance.md) |
| Premier appel très lent | Space en veille (inactivité) | Normal sur l'offre gratuite |

---
title: Turnover API
emoji: 📊
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# turnover_model

API FastAPI de prédiction du turnover (Random Forest), déployée sur Hugging Face Spaces.

## Base de données locale (PostgreSQL)

```bash
docker compose up -d db          # PostgreSQL 17 sur localhost:5433
pip install -r requirements.txt
python -m src.db.init_db         # crée les tables (sql/01_schema.sql) et charge la fusion des 3 CSV
python -m src.train              # entraîne depuis la base, exporte model/pipeline.joblib
docker compose up -d --build api # API sur http://localhost:7860/docs
```

- `employes` : entrées du modèle (jeu initial + chaque appel à `/predict`).
- `predictions` : sorties, liées à `employes` par clé étrangère.
  `origine = 'observation'` (départ réel, sans probabilité ni seuil) ou `'prediction'`.
- Fichiers SQL dans [`sql/`](sql/), requêtes de consultation dans `sql/02_requetes_utiles.sql`.
- Connexion configurable via `DATABASE_URL` (par défaut : la base de `docker-compose.yml`).
  Sur Hugging Face, sans PostgreSQL, l'API utilise un fichier SQLite non persistant.

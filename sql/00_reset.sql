-- Supprime les tables (ET TOUTES LES DONNÉES, prédictions comprises).
-- Appliqué par : python -m src.db.init_db --reset
DROP TABLE IF EXISTS predictions;
DROP TABLE IF EXISTS employes;

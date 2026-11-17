-- Supprime les tables (ET TOUTES LES DONNÉES : prédictions, journal et comptes compris).
-- Appliqué par : python -m src.db.init_db --reset
DROP TABLE IF EXISTS interactions;
DROP TABLE IF EXISTS predictions;
DROP TABLE IF EXISTS employes;
DROP TABLE IF EXISTS utilisateurs;

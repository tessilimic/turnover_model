-- Rôles PostgreSQL à privilèges minimaux (principe du moindre privilège).
-- Appliqué par : python -m src.db.init_db (connexion administrateur), après 01_schema.sql.
-- Idempotent. Les mots de passe ne sont PAS dans ce fichier : init_db les définit à
-- partir des variables d'environnement (voir docs/securite.md).
--
-- | Rôle               | Usage                       | Droits                                        |
-- |--------------------|-----------------------------|-----------------------------------------------|
-- | (propriétaire)     | init_db, migrations         | Tous (crée les tables)                        |
-- | turnover_api       | l'API                       | Écrire prédictions et journal, lire comptes   |
-- | turnover_ml        | src.train                   | Lire les données d'entraînement uniquement    |
-- | turnover_auditeur  | analyste, contrôle          | Lire résultats et journal, SANS données RH     |
--
-- Aucun rôle applicatif ne peut modifier ni supprimer une prédiction ou une ligne du
-- journal : la piste d'audit est en ajout seul.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'turnover_api') THEN
        CREATE ROLE turnover_api NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'turnover_ml') THEN
        CREATE ROLE turnover_ml NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'turnover_auditeur') THEN
        CREATE ROLE turnover_auditeur NOLOGIN;
    END IF;
END
$$;

-- Personne d'autre que le propriétaire n'a de droit par défaut.
REVOKE ALL ON employes, predictions, interactions, utilisateurs FROM PUBLIC;
REVOKE ALL ON employes, predictions, interactions, utilisateurs
    FROM turnover_api, turnover_ml, turnover_auditeur;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO turnover_api, turnover_ml, turnover_auditeur;

-- API : enregistre les prédictions et le journal ; ne relit pas les données RH.
-- (SELECT sur id et cree_le : nécessaire à INSERT ... RETURNING.)
GRANT INSERT ON employes, predictions, interactions TO turnover_api;
GRANT SELECT (id, cree_le) ON employes, predictions TO turnover_api;
GRANT SELECT ON interactions TO turnover_api;                       -- GET /logs
GRANT SELECT ON utilisateurs TO turnover_api;                       -- authentification
GRANT UPDATE (echecs_connexion, verrouille_jusqu_a, derniere_connexion)
    ON utilisateurs TO turnover_api;                                -- pas le mot de passe ni le rôle

-- Entraînement : lecture seule des entrées et des départs observés.
GRANT SELECT ON employes, predictions TO turnover_ml;

-- Auditeur : résultats et journal, sans les données RH ni l'adresse du client.
GRANT SELECT ON predictions TO turnover_auditeur;
GRANT SELECT (id, request_id, cree_le, methode, route, code_http, duree_ms,
              prediction_id, version_api, empreinte_modele, utilisateur)
    ON interactions TO turnover_auditeur;

-- Consultation du journal des interactions (table interactions). Voir docs/logs.md.
-- docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < sql/04_journal.sql

-- 1. Derniers appels, avec la prédiction produite
SELECT i.cree_le, i.request_id, i.code_http, i.duree_ms,
       ROUND(p.probabilite::numeric, 4) AS probabilite, p.depart,
       i.empreinte_modele
FROM interactions i
LEFT JOIN predictions p ON p.id = i.prediction_id
ORDER BY i.id DESC
LIMIT 20;

-- 2. Répartition par code HTTP sur 7 jours, avec la durée au 95e percentile
SELECT code_http,
       COUNT(*)                                                         AS nb,
       ROUND(AVG(duree_ms)::numeric, 1)                                 AS duree_moyenne_ms,
       ROUND(percentile_cont(0.95) WITHIN GROUP (ORDER BY duree_ms)::numeric, 1) AS duree_p95_ms
FROM interactions
WHERE cree_le >= now() - interval '7 days'
GROUP BY code_http
ORDER BY code_http;

-- 3. Champs le plus souvent refusés (erreurs de validation)
SELECT e ->> 'loc'  AS champ,
       e ->> 'type' AS type_erreur,
       COUNT(*)     AS nb
FROM interactions, jsonb_array_elements(erreurs) AS e
WHERE code_http = 422
GROUP BY 1, 2
ORDER BY nb DESC
LIMIT 10;

-- 4. Retrouver tout le parcours d'une requête (remplacer l'identifiant)
SELECT i.*, p.probabilite, p.seuil, p.depart, e.id AS employe_id
FROM interactions i
LEFT JOIN predictions p ON p.id = i.prediction_id
LEFT JOIN employes e ON e.id = p.employe_id
WHERE i.request_id = 'REMPLACER-PAR-LE-X-REQUEST-ID';

-- 5. Purge (durée de conservation : 12 mois, voir docs/logs.md).
--    À exécuter volontairement, décommenter pour l'utiliser :
-- DELETE FROM interactions WHERE cree_le < now() - interval '12 months';

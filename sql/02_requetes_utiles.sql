-- Requêtes de consultation (lecture seule).
-- Exemple : docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < sql/02_requetes_utiles.sql

-- 1. Volume par origine
SELECT origine,
       COUNT(*)                                  AS nb,
       ROUND(AVG(depart::int) * 100, 1)          AS pct_depart,
       ROUND(AVG(probabilite)::numeric, 3)       AS proba_moyenne
FROM predictions
GROUP BY origine
ORDER BY origine;

-- 2. Dernières prédictions de l'API, avec quelques entrées
SELECT p.id, p.cree_le, ROUND(p.probabilite::numeric, 4) AS probabilite, p.seuil, p.depart,
       e.age, e.poste, e.revenu_mensuel, e.heure_supplementaires
FROM predictions p
JOIN employes e ON e.id = p.employe_id
WHERE p.origine = 'prediction'
ORDER BY p.cree_le DESC
LIMIT 10;

-- 3. Contrôle d'intégrité : employés sans aucune sortie (attendu : 0)
SELECT COUNT(*) AS employes_sans_sortie
FROM employes e
WHERE NOT EXISTS (SELECT 1 FROM predictions p WHERE p.employe_id = e.id);

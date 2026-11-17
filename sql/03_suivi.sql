-- Suivi mensuel des prédictions (lecture seule). Voir docs/maintenance.md.
-- docker compose exec -T db psql -U turnover -d turnover < sql/03_suivi.sql

-- 1. Prédictions par mois : volume, probabilité moyenne, part de départs prédits
SELECT date_trunc('month', cree_le)::date            AS mois,
       COUNT(*)                                      AS nb_predictions,
       ROUND(AVG(probabilite)::numeric, 3)           AS proba_moyenne,
       ROUND(AVG(depart::int) * 100, 1)              AS pct_depart_predit
FROM predictions
WHERE origine = 'prediction'
GROUP BY 1
ORDER BY 1 DESC;

-- 2. Distribution des probabilités (tranches de 0,1)
SELECT ROUND((width_bucket(probabilite, 0, 1, 10) - 1) / 10.0, 1) AS tranche_min,
       COUNT(*)                                      AS nb
FROM predictions
WHERE origine = 'prediction'
GROUP BY 1
ORDER BY 1;

-- 3. Profil des employés évalués ce mois-ci, comparé au jeu d'entraînement
SELECT CASE WHEN e.id_employee IS NULL THEN 'API (30 derniers jours)' ELSE 'entraînement' END AS population,
       COUNT(*)                                      AS nb,
       ROUND(AVG(e.age), 1)                          AS age_moyen,
       ROUND(AVG(e.revenu_mensuel))                  AS revenu_moyen,
       ROUND(AVG((e.heure_supplementaires = 'Oui')::int) * 100, 1) AS pct_heures_sup
FROM employes e
WHERE e.id_employee IS NOT NULL
   OR e.cree_le >= now() - interval '30 days'
GROUP BY 1;

-- 4. Comparaison prédiction / départ réel, pour les employés ayant les deux
SELECT COUNT(*)                                                    AS nb_employes,
       SUM((p.depart AND o.depart)::int)                           AS departs_detectes,
       SUM((NOT p.depart AND o.depart)::int)                       AS departs_rates,
       SUM((p.depart AND NOT o.depart)::int)                       AS fausses_alertes
FROM predictions p
JOIN predictions o ON o.employe_id = p.employe_id AND o.origine = 'observation'
WHERE p.origine = 'prediction';

# Performances

Toutes les valeurs sont issues du notebook (`notebooks/turnover_modeling.ipynb`) et
reproduites à l'identique par `python -m src.train` (vérifié par un test d'intégration).

## Métriques utilisées

| Métrique | Question à laquelle elle répond |
|---|---|
| **Recall** (rappel) | Parmi les départs réels, combien sont détectés ? |
| **Precision** | Parmi les alertes, combien sont de vrais départs ? |
| **F2** | Compromis donnant 2 fois plus de poids au recall (choix du seuil) |
| **ROC AUC** | Capacité à classer un partant avant un restant (0,5 = hasard, 1 = parfait), indépendante du seuil |
| **PR AUC** | Idem, mais centrée sur la classe rare (référence hasard : 0,16) |
| **Balanced accuracy** | Moyenne des taux de bonne détection des deux classes |

L'*accuracy* simple n'est pas utilisée : prédire « personne ne part » donne déjà 84 %.

## Résultats du modèle retenu (seuil 0,41)

| Métrique | Entraînement (CV) | Validation (CV, 5 plis) | **Test** (294 employés) |
|---|---|---|---|
| ROC AUC | 0,900 | 0,804 ± 0,025 | **0,769** |
| PR AUC | 0,692 | 0,547 ± 0,086 | **0,378** |
| Recall | 0,909 | 0,784 ± 0,057 | **0,809** |
| Precision | 0,369 | 0,318 ± 0,032 | **0,292** |
| F1 | 0,525 | 0,451 ± 0,035 | **0,429** |
| Balanced accuracy | 0,805 | 0,728 ± 0,033 | **0,718** |

### Matrice de confusion (test)

| | Prédit : reste | Prédit : part |
|---|---|---|
| **Réel : reste** (247) | 156 | 91 fausses alertes |
| **Réel : part** (47) | 9 départs ratés | **38 départs détectés** |

**Lecture métier** : sur 100 employés dont 16 partiront, le modèle en signale environ 44,
parmi lesquels 13 vrais départs ; 3 départs passent inaperçus.

## Modèles de référence

Comparaison du notebook (paramètres par défaut, seuil 0,5, sans les features créées) :

| Modèle | ROC AUC test | Recall test | Precision test | Remarque |
|---|---|---|---|---|
| Dummy (classe majoritaire) | 0,500 | 0,00 | — | Ne détecte aucun départ |
| Régression logistique | **0,823** | 0,36 | 0,65 | Meilleur classement, mais peu de départs détectés au seuil 0,5 |
| Random Forest par défaut | 0,804 | 0,13 | 0,55 | Surapprentissage : score parfait (1,000) en entraînement |
| **Random Forest retenue** | 0,769 | **0,81** | 0,29 | Régularisée, pondérée, seuil 0,41 |

!!! note "Point d'attention"
    La régression logistique de référence obtient un ROC AUC de test supérieur à la forêt
    retenue (0,823 contre 0,769). Les deux ne sont pas directement comparables (seuil,
    features, réglage), et le jeu de test ne contient que 47 départs, mais cet écart
    justifie une **réévaluation de la régression logistique** réglée dans les mêmes
    conditions : elle figure dans la [feuille de route](maintenance.md#feuille-de-route).

## Surapprentissage

| | ROC AUC entraînement | ROC AUC validation | Écart |
|---|---|---|---|
| Random Forest par défaut | 1,000 | 0,824 | 0,176 |
| **Random Forest retenue** | 0,900 | 0,804 | **0,096** |

La régularisation (profondeur 4, feuilles de 20 employés) divise l'écart par deux.

## Garde-fous automatiques

Vérifiés par les tests d'intégration à chaque PR :

- l'entraînement reproduit les métriques du notebook (ROC AUC 0,769 ± 0,001, recall 0,81 ± 0,01) ;
- le modèle exporté a un ROC AUC > 0,75 sur les données d'entraînement ;
- la version de scikit-learn du modèle est celle installée.

Critères d'acceptation d'un nouveau modèle : voir [Maintenance](maintenance.md#criteres-dacceptation).

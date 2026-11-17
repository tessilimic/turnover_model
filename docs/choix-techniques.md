# Choix techniques

Chaque choix est présenté avec les alternatives écartées et ses contreparties.

## Modèle

### Random Forest

| | |
|---|---|
| **Pourquoi** | Capte les effets non linéaires et les interactions (ex. heures sup. × déplacements) sans les coder ; peu sensible aux échelles ; fournit des importances et se prête à SHAP. |
| **Alternatives** | Régression logistique (plus simple, plus explicable), gradient boosting (souvent plus performant, plus de réglages). |
| **Contreparties** | La forêt par défaut surapprend fortement : elle a été régularisée (profondeur 4, feuilles ≥ 20). La régression logistique de référence a un meilleur ROC AUC de test (0,823 contre 0,769) : à réévaluer, voir [Performances](performances.md#modeles-de-reference). |

### Seuil à 0,41 (F2)

Le coût d'un départ non détecté (recrutement, perte de compétences) dépasse celui d'une
fausse alerte (un entretien). Le seuil maximise donc le F2, qui privilégie le rappel.
Contrepartie : précision d'environ 30 %.

### Pipeline unique exporté avec joblib

Features, encodage et forêt sont dans **un seul objet** : l'API ne peut pas appliquer un
prétraitement différent de celui de l'entraînement. `joblib` est le format standard de
scikit-learn. Contrepartie : le fichier n'est relisible qu'avec la **même version** de
scikit-learn, d'où les versions figées (`==`) et le test qui le vérifie.

### Réentraînement sur 100 % des données

Après évaluation sur le test (80/20), le modèle exporté est réentraîné sur les 1 470
lignes : avec si peu de données, se priver de 20 % coûterait plus que cela ne protège.
Les métriques publiées restent celles du test.

## API

### FastAPI + Pydantic

| | |
|---|---|
| **Pourquoi** | Documentation **Swagger générée automatiquement** à partir du code (donc toujours à jour) ; validation des entrées déclarative ; performances ; typage. |
| **Alternatives** | Flask (pas de validation ni de Swagger natifs), Django REST (trop lourd pour 2 routes). |

Choix de validation :

- **Listes fermées** (`Literal`) pour les champs texte : seules les valeurs vues à
  l'entraînement passent, et Swagger les affiche en liste déroulante ;
- **`extra="forbid"`** : un champ mal orthographié est refusé au lieu d'être ignoré
  silencieusement (ce qui aurait donné une prédiction fausse) ;
- **noms de champs identiques aux sources**, fautes comprises : aucune table de
  correspondance à maintenir entre CSV, base, modèle et API.

### Modèle chargé au démarrage

Une erreur (fichier absent, corrompu) empêche l'API de démarrer : elle est visible
immédiatement dans les logs du Space, au lieu d'apparaître à la première requête.

### Logs et traçabilité

| Choix | Pourquoi |
|---|---|
| **Logs JSON sur la sortie standard** | Standard des conteneurs (Docker, Hugging Face les collectent) ; une ligne JSON se filtre avec `jq` et s'importe dans n'importe quel outil (ELK, Loki, Datadog). Fichier en option seulement. |
| **`request_id` partout** (`contextvars`) | Relie la requête HTTP, le calcul du modèle, chaque requête SQL et la ligne du journal, sans passer l'identifiant de fonction en fonction. Repris de `X-Request-ID` pour suivre un appel depuis le système client. |
| **Événements SQLAlchemy** | Toutes les requêtes SQL sont tracées sans modifier le code métier ; les valeurs des paramètres sont exclues (données RH). |
| **Journal en base, séparé des logs** | Les logs techniques sont volatils et non structurés pour l'analyse ; la table `interactions` est interrogeable en SQL, reliée aux prédictions, et conservée selon une durée maîtrisée. |
| **Écrit par un middleware** | Couvre aussi les appels refusés (422) ou en erreur (500), qui n'atteignent jamais le code de `/predict`. Un échec d'écriture du journal ne fait pas échouer la réponse. |
| **`GET /logs` protégé par clé, désactivé par défaut** | Le Space est public et le journal contient des données RH : sans clé configurée, l'endpoint répond 403. Données d'entrée masquées sauf demande explicite. Alternative écartée : un fichier téléchargeable (pas de filtre, pas de contrôle d'accès). |

## Sécurité

| Choix | Pourquoi | Alternative écartée |
|---|---|---|
| **OAuth2 *password* + JWT** | Standard intégré à FastAPI et à Swagger (bouton *Authorize*) ; jeton à durée limitée, lié à une personne | Clé d'API partagée : ni expiration, ni traçabilité individuelle |
| **Compte relu à chaque requête** | Désactivation et changement de rôle immédiats, malgré des jetons sans état | Liste de révocation : plus complexe, inutile à cette échelle |
| **Argon2id** | Recommandé par l'OWASP, résistant aux GPU, sel intégré | bcrypt (acceptable, plus ancien), SHA-256 (inadapté aux mots de passe) |
| **Rôles applicatifs `rh` / `auditeur` / `admin`** | Séparation des tâches : qui prédit ne contrôle pas | Un rôle unique |
| **Comptes gérés en ligne de commande** | Aucune route d'API ne peut créer un compte ou élever un rôle : surface d'attaque réduite | Route d'administration |
| **Un rôle PostgreSQL par programme** | Une faille de l'API ne permet ni de modifier l'historique, ni de relire les données RH, ni de créer un compte | Un seul utilisateur propriétaire pour tout |
| **Secrets uniquement dans l'environnement** | Rien dans le dépôt ; aucune valeur par défaut qui finirait en production | Valeurs de développement dans le code |
| **pip-audit + bandit en CI** | Détection automatique des dépendances vulnérables et des erreurs de code courantes | Revue manuelle seule |

Détails : [Sécurité et accès](securite.md).

## Données

### PostgreSQL + SQLAlchemy (ORM)

| | |
|---|---|
| **Pourquoi PostgreSQL** | Base relationnelle standard, contraintes riches (CHECK, index partiel), outillage. |
| **Pourquoi SQLAlchemy** | Un seul code pour PostgreSQL et SQLite ; requêtes typées ; pas de SQL concaténé (pas d'injection). |
| **Pourquoi Docker Compose** | Aucune installation sous Windows ; même version (17) en local et en CI ; port 5433 pour cohabiter avec un PostgreSQL existant. |

### Fichiers SQL comme source de vérité du schéma

Sur PostgreSQL, les tables sont créées par `sql/01_schema.sql` (versionné, lisible,
relu en PR). Les modèles ORM en sont le miroir ; un test d'intégration vérifie que les
colonnes coïncident, sur un vrai PostgreSQL en CI.
Alternative écartée : Alembic (migrations). Utile quand le schéma évoluera sur une base
contenant des données de production : voir la [feuille de route](maintenance.md#feuille-de-route).

### Deux tables : `employes` / `predictions`

Les entrées et les sorties sont séparées et reliées par clé étrangère. Une même table
`predictions` contient les **observations** (départ réel, jeu initial) et les
**prédictions** (API) : on peut ainsi, plus tard, comparer prédictions et départs réels
pour un même employé. Les contraintes en base empêchent les lignes incohérentes, quel
que soit le programme qui écrit.

### SQLite sur Hugging Face

Le Space gratuit n'a pas de PostgreSQL. Plutôt que de désactiver l'enregistrement,
l'image utilise un fichier SQLite : l'API reste fonctionnelle et identique.
Contrepartie : les prédictions sont perdues au redémarrage du Space. Pour les conserver,
pointer `DATABASE_URL` vers un PostgreSQL hébergé (secret du Space).

## Déploiement

### Docker

Le même environnement en local, en CI et en production. L'image n'embarque que l'API,
`src/` et le modèle (`.dockerignore` exclut données, notebook, tests, documentation) ;
elle s'exécute avec un utilisateur non root (UID 1000, exigé par Hugging Face).

### Hugging Face Spaces

| | |
|---|---|
| **Pourquoi** | Gratuit, conçu pour le Machine Learning, déploiement Docker par simple `git push`. |
| **Alternatives** | Render / Railway (mise en veille similaire), AWS / Azure / GCP (plus proches d'une production d'entreprise, mais configuration et coûts). |
| **Contreparties** | Mise en veille après inactivité (premier appel lent), pas de base persistante, fichiers binaires obligatoirement en Git LFS. |

### Git LFS pour le modèle

Hugging Face refuse les fichiers binaires hors LFS/Xet. LFS garde aussi le dépôt léger
quand le modèle est réentraîné : chaque version du `.joblib` n'est pas copiée dans
l'historique Git.

### GitHub Actions, CI/CD en deux workflows

`ci.yaml` (tests, build Docker, documentation) tourne sur chaque push et PR ;
`deploy.yaml` la **réutilise** puis déploie, uniquement sur `main`. Tout passe par des
PR : rien n'arrive en production sans tests verts.

## Qualité

### Trois catégories de tests

Les tests unitaires (sans base, faux modèle) tournent en quelques secondes et localisent
précisément une erreur ; les tests d'intégration vérifient la vraie base et le vrai
modèle ; les tests fonctionnels vérifient le contrat HTTP. Le marqueur est déduit du
dossier : impossible d'oublier de classer un test.

### Documentation : Swagger, Markdown, MkDocs, Sphinx

| Outil | Pourquoi |
|---|---|
| Swagger | Généré depuis le code : la référence de l'API ne peut pas diverger. Exporté dans ce site, avec un test qui détecte un export périmé. |
| Markdown | Lisible directement sur GitHub, relu en PR comme le code. |
| MkDocs (Material) | Site de documentation à partir du Markdown : navigation, recherche, diagrammes Mermaid. |
| Sphinx (autodoc) | Référence du code générée depuis les docstrings : documentation au plus près du code. |

La CI construit la documentation en mode strict : un lien cassé ou une docstring
invalide fait échouer la PR.

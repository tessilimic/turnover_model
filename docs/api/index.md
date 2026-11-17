# Référence de l'API (Swagger)

Référence complète générée à partir du code (OpenAPI 3.1) : routes, schémas,
contraintes de chaque champ, exemples et codes d'erreur.

- Sur l'API en fonctionnement, la même interface est **interactive** sur `/docs`
  (bouton *Try it out*) ; ReDoc est disponible sur `/redoc`.
- Le schéma brut est téléchargeable : [openapi.json](openapi.json).

!!! note "Mise à jour"
    Ce schéma est exporté par `python -m scripts.export_openapi`. Un test unitaire
    échoue s'il n'est plus à jour par rapport au code de l'API.

<swagger-ui src="openapi.json"/>

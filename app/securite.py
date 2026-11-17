"""En-têtes HTTP de sécurité, ajoutés à chaque réponse.

Deux politiques selon la page :

* **réponses de l'API** (JSON : ``/predict``, ``/logs``...) : aucune ressource, aucun
  affichage dans un cadre, aucune mise en cache ;
* **pages de documentation** (``/``, ``/docs``, ``/redoc``) : Swagger UI charge ses
  scripts depuis un CDN, et l'onglet *App* de Hugging Face Spaces l'affiche dans un
  cadre (iframe) de huggingface.co. L'affichage en cadre y est donc autorisé, mais
  uniquement pour les origines de :func:`origines_cadre`.
"""

import os

from fastapi import Request

ENTETES_COMMUNS = {
    "X-Content-Type-Options": "nosniff",                       # pas d'interprétation du type
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",  # HTTPS uniquement
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

ENTETES_API = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "X-Frame-Options": "DENY",    # jamais dans un cadre (anciens navigateurs)
    "Cache-Control": "no-store",  # réponses contenant des données RH ou des jetons
}


def origines_cadre() -> str:
    """Origines autorisées à afficher la documentation dans un cadre.

    Variable ``FRAME_ANCESTORS`` (séparées par des espaces), par défaut
    ``https://huggingface.co`` : l'onglet *App* du Space.
    """
    return os.getenv("FRAME_ANCESTORS", "https://huggingface.co")


def est_page_documentation(chemin: str) -> bool:
    """``/`` (redirection vers Swagger), ``/docs`` (et sa page OAuth2) et ``/redoc``."""
    return chemin == "/" or chemin.startswith(("/docs", "/redoc"))


async def entetes_securite(request: Request, call_next):
    """Middleware HTTP : ajoute les en-têtes communs, puis ceux de l'API ou de la documentation."""
    response = await call_next(request)
    response.headers.update(ENTETES_COMMUNS)
    if est_page_documentation(request.url.path):
        # Pas de X-Frame-Options ici : il ne sait pas autoriser une origine précise.
        response.headers["Content-Security-Policy"] = f"frame-ancestors 'self' {origines_cadre()}"
    else:
        response.headers.update(ENTETES_API)
    return response

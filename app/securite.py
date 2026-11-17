"""En-têtes HTTP de sécurité, ajoutés à chaque réponse."""

from fastapi import Request

#: Pages servant du HTML (Swagger UI, ReDoc) : elles chargent leurs scripts depuis un CDN,
#: la politique de contenu stricte ne leur est donc pas appliquée.
PAGES_DOCUMENTATION = ("/docs", "/redoc")

ENTETES_COMMUNS = {
    "X-Content-Type-Options": "nosniff",                       # pas d'interprétation du type
    "X-Frame-Options": "DENY",                                 # pas d'affichage dans un cadre
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",  # HTTPS uniquement
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

ENTETES_API = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Cache-Control": "no-store",  # réponses contenant des données RH ou des jetons
}


async def entetes_securite(request: Request, call_next):
    """Middleware HTTP : ajoute :data:`ENTETES_COMMUNS`, et :data:`ENTETES_API` hors documentation."""
    response = await call_next(request)
    response.headers.update(ENTETES_COMMUNS)
    if not request.url.path.startswith(PAGES_DOCUMENTATION):
        response.headers.update(ENTETES_API)
    return response

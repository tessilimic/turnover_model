from fastapi import FastAPI
from fastapi.responses import RedirectResponse

app = FastAPI(
    title="Turnover API",
    description="API de prédiction du turnover des employés.",
    version="0.1.0",
)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Page d'accueil du Space : redirige vers Swagger UI."""
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["monitoring"])
def health() -> dict[str, str]:
    """Vérifie que l'API est en ligne."""
    return {"status": "ok"}

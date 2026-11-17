"""Connexion à la base et création du schéma."""

import os
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

from src.db.models import Base

# Base locale lancée par docker-compose.yml (identifiants de développement uniquement).
URL_PAR_DEFAUT = "postgresql+psycopg://turnover:turnover@localhost:5433/turnover"
DOSSIER_SQL = Path(__file__).resolve().parents[2] / "sql"


def get_database_url() -> str:
    """Adresse de la base : variable ``DATABASE_URL``, sinon :data:`URL_PAR_DEFAUT`."""
    return os.getenv("DATABASE_URL", URL_PAR_DEFAUT)


@lru_cache
def get_engine() -> Engine:
    """Connexion SQLAlchemy partagée (créée au premier appel).

    Sous SQLite, active les clés étrangères (désactivées par défaut).
    """
    engine = create_engine(get_database_url())
    if engine.dialect.name == "sqlite":
        # SQLite n'applique les clés étrangères que si on le lui demande.
        event.listen(engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    return engine


def get_session() -> Iterator[Session]:
    """Une session par requête (dépendance FastAPI)."""
    with Session(get_engine()) as session:
        yield session


def _executer_fichier_sql(engine: Engine, nom: str) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql((DOSSIER_SQL / nom).read_text(encoding="utf-8"))


def creer_schema(engine: Engine) -> None:
    """Crée les tables si besoin : fichiers SQL sur PostgreSQL, ORM sinon (SQLite)."""
    if engine.dialect.name == "postgresql":
        _executer_fichier_sql(engine, "01_schema.sql")
    else:
        Base.metadata.create_all(engine)


def supprimer_schema(engine: Engine) -> None:
    """Supprime les tables et toutes leurs données."""
    if engine.dialect.name == "postgresql":
        _executer_fichier_sql(engine, "00_reset.sql")
    else:
        Base.metadata.drop_all(engine)

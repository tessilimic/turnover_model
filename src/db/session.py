"""Connexion à la base et création du schéma."""

import logging
import os
import time
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

from src.db.models import Base

# Base locale lancée par docker-compose.yml (identifiants de développement uniquement).
URL_PAR_DEFAUT = "postgresql+psycopg://turnover:turnover@localhost:5433/turnover"
DOSSIER_SQL = Path(__file__).resolve().parents[2] / "sql"

journal = logging.getLogger("turnover.db")


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
    tracer_requetes_sql(engine)
    journal.info(
        "connexion à la base configurée",
        extra={"evenement": "db.configuration", "dialecte": engine.dialect.name,
               "url": engine.url.render_as_string(hide_password=True)},
    )
    return engine


def tracer_requetes_sql(engine: Engine) -> None:
    """Journalise chaque requête SQL (texte, durée, lignes), validation et annulation.

    Les **valeurs** des paramètres ne sont jamais journalisées (données RH) :
    seul le texte de la requête, avec ses marqueurs, l'est.
    """

    @event.listens_for(engine, "before_cursor_execute")
    def _debut(conn, cursor, statement, parameters, context, executemany):
        conn.info.setdefault("debuts_requetes", []).append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _fin(conn, cursor, statement, parameters, context, executemany):
        duree = (time.perf_counter() - conn.info["debuts_requetes"].pop()) * 1000
        journal.info(
            "requête SQL",
            extra={"evenement": "db.requete", "sql": " ".join(statement.split())[:500],
                   "duree_ms": round(duree, 2), "lignes": cursor.rowcount},
        )

    @event.listens_for(engine, "commit")
    def _validation(conn):
        journal.info("transaction validée", extra={"evenement": "db.commit"})

    @event.listens_for(engine, "rollback")
    def _annulation(conn):
        journal.info("transaction annulée", extra={"evenement": "db.rollback"})

    @event.listens_for(engine, "handle_error")
    def _erreur(contexte):
        conn = contexte.connection
        if conn is not None and conn.info.get("debuts_requetes"):
            conn.info["debuts_requetes"].pop()
        journal.error(
            "erreur SQL",
            extra={"evenement": "db.erreur", "erreur": type(contexte.original_exception).__name__,
                   "sql": " ".join((contexte.statement or "").split())[:500]},
        )


def get_session() -> Iterator[Session]:
    """Une session par requête (dépendance FastAPI).

    ``expire_on_commit=False`` : après la validation, les objets restent lisibles
    sans nouvelle requête SQL (ex. l'identifiant de la prédiction créée).
    """
    with Session(get_engine(), expire_on_commit=False) as session:
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
    journal.info("schéma prêt", extra={"evenement": "db.schema", "dialecte": engine.dialect.name})


def supprimer_schema(engine: Engine) -> None:
    """Supprime les tables et toutes leurs données."""
    if engine.dialect.name == "postgresql":
        _executer_fichier_sql(engine, "00_reset.sql")
    else:
        Base.metadata.drop_all(engine)

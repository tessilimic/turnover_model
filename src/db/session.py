"""Connexion à la base, création du schéma et rôles d'accès.

Aucun identifiant n'est écrit dans le code : les adresses de connexion viennent de
variables d'environnement (ou du fichier ``.env``, jamais versionné). Chaque usage a
sa propre variable, donc son propre rôle PostgreSQL (moindre privilège) :

* ``DATABASE_URL`` : l'API (rôle ``turnover_api``) ;
* ``ML_DATABASE_URL`` : l'entraînement (rôle ``turnover_ml``, lecture seule) ;
* ``ADMIN_DATABASE_URL`` : ``init_db`` et la gestion des comptes (propriétaire).
"""

import logging
import os
import time
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from psycopg import sql
from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.orm import Session

from src.db.models import Base

DOSSIER_SQL = Path(__file__).resolve().parents[2] / "sql"

#: Rôles PostgreSQL applicatifs et variable contenant leur mot de passe.
ROLES_BASE = {
    "turnover_api": "TURNOVER_API_DB_PASSWORD",
    "turnover_ml": "TURNOVER_ML_DB_PASSWORD",
    "turnover_auditeur": "TURNOVER_AUDITEUR_DB_PASSWORD",
}

journal = logging.getLogger("turnover.db")

# Fichier .env local (secrets de développement) ; les variables déjà définies priment.
load_dotenv(override=False)


def get_database_url(variable: str = "DATABASE_URL") -> str:
    """Adresse de connexion lue dans ``variable``, à défaut dans ``DATABASE_URL``.

    Raises:
        RuntimeError: Si aucune des deux variables n'est définie.
    """
    url = os.getenv(variable) or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            f"{variable} n'est pas défini : copier .env.example en .env et le compléter "
            "(voir docs/securite.md)."
        )
    return url


def creer_engine(url: str) -> Engine:
    """Crée une connexion SQLAlchemy, avec la traçabilité des requêtes SQL.

    Sous SQLite, active les clés étrangères (désactivées par défaut).
    """
    # Délai de connexion borné : une base injoignable donne une erreur, pas une attente infinie.
    options = {"connect_timeout": 10} if url.startswith("postgresql") else {}
    engine = create_engine(url, connect_args=options)
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


@lru_cache
def get_engine() -> Engine:
    """Connexion partagée de l'API (``DATABASE_URL``), créée au premier appel."""
    return creer_engine(get_database_url())


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


def tables_manquantes(engine: Engine) -> list[str]:
    """Tables du modèle ORM absentes de la base (vide si le schéma est complet)."""
    existantes = set(inspect(engine).get_table_names())
    return sorted(set(Base.metadata.tables) - existantes)


def appliquer_roles(engine: Engine) -> list[str]:
    """Crée les rôles PostgreSQL et leurs droits (``sql/05_roles.sql``).

    Pour chaque rôle dont la variable de mot de passe est définie (:data:`ROLES_BASE`),
    autorise la connexion avec ce mot de passe ; PostgreSQL ne le stocke que sous forme
    d'empreinte SCRAM-SHA-256. La requête passe par la connexion brute du pilote :
    elle n'apparaît donc pas dans les logs SQL (le mot de passe non plus).

    Args:
        engine: Connexion **administrateur** (propriétaire des tables).

    Returns:
        Les rôles pour lesquels un mot de passe a été défini.
    """
    _executer_fichier_sql(engine, "05_roles.sql")
    actives = []
    connexion = engine.raw_connection()
    try:
        with connexion.cursor() as curseur:
            for role, variable in ROLES_BASE.items():
                if mot_de_passe := os.getenv(variable):
                    curseur.execute(sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                        sql.Identifier(role), sql.Literal(mot_de_passe)
                    ))
                    actives.append(role)
        connexion.commit()
    finally:
        connexion.close()
    journal.info("rôles appliqués", extra={"evenement": "db.roles", "roles_actives": actives})
    return actives

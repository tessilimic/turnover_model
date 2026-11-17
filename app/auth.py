"""Authentification (OAuth2 « password » + jetons JWT) et contrôle d'accès par rôle.

1. ``POST /token`` : identifiant + mot de passe -> jeton JWT signé (durée limitée).
2. Chaque requête protégée envoie ``Authorization: Bearer <jeton>``.
3. Le compte est relu en base à chaque requête : un compte désactivé ou dont le rôle
   change perd ses droits immédiatement, sans attendre l'expiration du jeton.

Mots de passe : seule l'empreinte **Argon2id** (sel aléatoire, recommandation OWASP)
est stockée. Après :data:`ECHECS_AVANT_VERROUILLAGE` échecs, le compte est verrouillé
:data:`DUREE_VERROUILLAGE`.

Configuration :

* ``JWT_SECRET`` : clé de signature des jetons (32 caractères minimum). Si elle est
  absente, une clé aléatoire est générée au démarrage (les jetons ne survivent alors
  pas à un redémarrage) ;
* ``JWT_DUREE_MINUTES`` : durée de validité d'un jeton (30 par défaut).
"""

import logging
import os
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.db.models import Utilisateur
from src.db.session import get_session

journal = logging.getLogger("turnover.auth")

ROLES = ("admin", "rh", "auditeur")
ALGORITHME = "HS256"
EMETTEUR = "turnover-api"
LONGUEUR_MIN_MOT_DE_PASSE = 12
LONGUEUR_MIN_SECRET = 32
ECHECS_AVANT_VERROUILLAGE = 5
DUREE_VERROUILLAGE = timedelta(minutes=15)

_hacheur = PasswordHasher()  # Argon2id, paramètres par défaut recommandés par argon2-cffi
# Empreinte factice : vérifiée quand l'identifiant n'existe pas, pour que la durée de
# réponse ne révèle pas si un compte existe (énumération des comptes).
_EMPREINTE_FACTICE = _hacheur.hash(secrets.token_urlsafe(16))

schema_oauth2 = OAuth2PasswordBearer(
    tokenUrl="token",
    description="Se connecter avec un identifiant et un mot de passe (bouton Authorize).",
)


# ---------------------------------------------------------------- mots de passe

def verifier_politique(mot_de_passe: str) -> None:
    """Refuse un mot de passe trop faible.

    Raises:
        ValueError: Moins de 12 caractères, ou une seule catégorie de caractères.
    """
    if len(mot_de_passe) < LONGUEUR_MIN_MOT_DE_PASSE:
        raise ValueError(f"au moins {LONGUEUR_MIN_MOT_DE_PASSE} caractères requis")
    categories = [str.islower, str.isupper, str.isdigit, lambda c: not c.isalnum()]
    if sum(any(test(c) for c in mot_de_passe) for test in categories) < 3:
        raise ValueError("mélanger au moins 3 types : minuscules, majuscules, chiffres, symboles")


def hacher_mot_de_passe(mot_de_passe: str) -> str:
    """Empreinte Argon2id du mot de passe (sel aléatoire inclus)."""
    return _hacheur.hash(mot_de_passe)


def verifier_mot_de_passe(empreinte: str, mot_de_passe: str) -> bool:
    """Compare un mot de passe à son empreinte (comparaison en temps constant)."""
    try:
        return _hacheur.verify(empreinte, mot_de_passe)
    except (VerificationError, InvalidHashError):
        return False


# ---------------------------------------------------------------- jetons JWT

@lru_cache
def get_secret_jwt() -> str:
    """Clé de signature des jetons (``JWT_SECRET``, ou aléatoire à défaut)."""
    secret = os.getenv("JWT_SECRET")
    if not secret:
        journal.warning(
            "JWT_SECRET non défini : clé aléatoire générée, les jetons seront invalidés "
            "au prochain redémarrage", extra={"evenement": "auth.secret_genere"},
        )
        return secrets.token_urlsafe(48)
    if len(secret) < LONGUEUR_MIN_SECRET:
        raise RuntimeError(f"JWT_SECRET trop court ({LONGUEUR_MIN_SECRET} caractères minimum)")
    return secret


def duree_jeton() -> timedelta:
    return timedelta(minutes=int(os.getenv("JWT_DUREE_MINUTES", "30")))


def creer_jeton(identifiant: str, role: str, maintenant: datetime | None = None) -> str:
    """Jeton JWT signé : identifiant (``sub``), rôle, date d'émission et d'expiration."""
    maintenant = maintenant or datetime.now(UTC)
    charge = {
        "sub": identifiant, "role": role, "iss": EMETTEUR,
        "iat": maintenant, "exp": maintenant + duree_jeton(),
    }
    return jwt.encode(charge, get_secret_jwt(), algorithm=ALGORITHME)


def decoder_jeton(jeton: str) -> dict:
    """Vérifie la signature, l'émetteur et l'expiration d'un jeton.

    Raises:
        jwt.InvalidTokenError: Jeton expiré, falsifié, d'un autre émetteur ou
            signé avec un autre algorithme (``none`` compris).
    """
    return jwt.decode(
        jeton, get_secret_jwt(), algorithms=[ALGORITHME], issuer=EMETTEUR,
        options={"require": ["sub", "exp", "iat", "iss"]},
    )


# ---------------------------------------------------------------- verrouillage

def est_verrouille(utilisateur: Utilisateur, maintenant: datetime) -> bool:
    fin = utilisateur.verrouille_jusqu_a
    if fin is not None and fin.tzinfo is None:  # SQLite ne conserve pas le fuseau
        fin = fin.replace(tzinfo=UTC)
    return fin is not None and fin > maintenant


def enregistrer_echec(utilisateur: Utilisateur, maintenant: datetime) -> None:
    """Compte un échec ; verrouille le compte au-delà du seuil."""
    utilisateur.echecs_connexion += 1
    if utilisateur.echecs_connexion >= ECHECS_AVANT_VERROUILLAGE:
        utilisateur.verrouille_jusqu_a = maintenant + DUREE_VERROUILLAGE
        utilisateur.echecs_connexion = 0
        journal.warning(
            "compte verrouillé", extra={"evenement": "auth.verrouillage",
                                        "identifiant": utilisateur.identifiant},
        )


def enregistrer_succes(utilisateur: Utilisateur, maintenant: datetime) -> None:
    utilisateur.echecs_connexion = 0
    utilisateur.verrouille_jusqu_a = None
    utilisateur.derniere_connexion = maintenant


def authentifier(session: Session, identifiant: str, mot_de_passe: str) -> Utilisateur | None:
    """Vérifie les identifiants ; renvoie le compte, ou ``None`` (raison non divulguée)."""
    maintenant = datetime.now(UTC)
    utilisateur = session.scalars(
        select(Utilisateur).where(Utilisateur.identifiant == identifiant)
    ).first()

    if utilisateur is None:
        verifier_mot_de_passe(_EMPREINTE_FACTICE, mot_de_passe)  # même durée de réponse
        raison = "identifiant inconnu"
    elif not utilisateur.actif:
        raison = "compte désactivé"
    elif est_verrouille(utilisateur, maintenant):
        raison = "compte verrouillé"
    elif not verifier_mot_de_passe(utilisateur.mot_de_passe_hash, mot_de_passe):
        enregistrer_echec(utilisateur, maintenant)
        session.commit()
        raison = "mot de passe incorrect"
    else:
        enregistrer_succes(utilisateur, maintenant)
        session.commit()
        journal.info("connexion réussie", extra={"evenement": "auth.connexion",
                                                 "identifiant": identifiant})
        return utilisateur

    # Jamais le mot de passe dans les logs ; la raison exacte reste côté serveur.
    journal.warning("connexion refusée", extra={"evenement": "auth.refus",
                                                "identifiant": identifiant, "raison": raison})
    return None


# ---------------------------------------------------------------- dépendances FastAPI

NON_AUTHENTIFIE = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    "Authentification requise ou jeton invalide.",
    headers={"WWW-Authenticate": "Bearer"},
)


def utilisateur_courant(
    request: Request,
    jeton: Annotated[str, Depends(schema_oauth2)],
    session: Annotated[Session, Depends(get_session)],
) -> Utilisateur:
    """Compte associé au jeton ``Bearer`` de la requête.

    Raises:
        HTTPException: 401 si le jeton est absent, invalide, expiré, ou si le compte
            n'existe plus ou est désactivé.
    """
    try:
        identifiant = decoder_jeton(jeton)["sub"]
    except jwt.InvalidTokenError as erreur:
        journal.warning("jeton refusé", extra={"evenement": "auth.jeton_invalide",
                                               "erreur": type(erreur).__name__})
        raise NON_AUTHENTIFIE from None

    utilisateur = session.scalars(
        select(Utilisateur).where(Utilisateur.identifiant == identifiant)
    ).first()
    if utilisateur is None or not utilisateur.actif:
        raise NON_AUTHENTIFIE
    request.state.utilisateur = utilisateur.identifiant  # pour le journal des interactions
    return utilisateur


def exiger_role(*roles: str):
    """Dépendance : refuse (403) un utilisateur authentifié dont le rôle n'est pas listé."""

    def _verifier(utilisateur: Annotated[Utilisateur, Depends(utilisateur_courant)]) -> Utilisateur:
        if utilisateur.role not in roles:
            journal.warning("accès refusé", extra={
                "evenement": "auth.acces_refuse", "identifiant": utilisateur.identifiant,
                "role": utilisateur.role, "roles_autorises": list(roles),
            })
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Droits insuffisants pour cette action.")
        return utilisateur

    return _verifier


#: Qui peut faire quoi (voir docs/securite.md).
acces_prediction = exiger_role("rh", "admin")
acces_logs = exiger_role("auditeur", "admin")

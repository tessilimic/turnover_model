"""Gestion des comptes de l'API (ligne de commande, connexion administrateur).

Usage :
    python -m app.utilisateurs creer <identifiant> --role rh
    python -m app.utilisateurs lister
    python -m app.utilisateurs mot-de-passe <identifiant>
    python -m app.utilisateurs desactiver <identifiant>
    python -m app.utilisateurs activer <identifiant>
    python -m app.utilisateurs deverrouiller <identifiant>

Le mot de passe est saisi sans écho (deux fois), ou lu dans une variable
d'environnement (``--mot-de-passe-env NOM``) pour l'automatisation. Il n'est jamais
passé en argument de la commande (il resterait dans l'historique du terminal).
"""

import argparse
import getpass
import logging
import os
import re
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import ROLES, hacher_mot_de_passe, verifier_politique
from src.db.models import Utilisateur
from src.db.session import creer_engine, get_database_url

journal = logging.getLogger("turnover.auth")

_IDENTIFIANT_VALIDE = re.compile(r"^[a-z0-9._-]{3,50}$")


def creer_utilisateur(session: Session, identifiant: str, mot_de_passe: str, role: str) -> Utilisateur:
    """Crée un compte (empreinte Argon2id du mot de passe).

    Raises:
        ValueError: Identifiant invalide ou déjà pris, rôle inconnu, mot de passe faible.
    """
    if not _IDENTIFIANT_VALIDE.fullmatch(identifiant):
        raise ValueError("identifiant : 3 à 50 caractères parmi a-z, 0-9, '.', '_', '-'")
    if role not in ROLES:
        raise ValueError(f"rôle inconnu : choisir parmi {', '.join(ROLES)}")
    verifier_politique(mot_de_passe)
    if _trouver(session, identifiant) is not None:
        raise ValueError(f"l'identifiant {identifiant!r} existe déjà")

    utilisateur = Utilisateur(
        identifiant=identifiant, role=role, mot_de_passe_hash=hacher_mot_de_passe(mot_de_passe),
    )
    session.add(utilisateur)
    session.commit()
    journal.info("compte créé", extra={"evenement": "auth.compte_cree",
                                       "identifiant": identifiant, "role": role})
    return utilisateur


def changer_mot_de_passe(session: Session, identifiant: str, mot_de_passe: str) -> None:
    """Remplace le mot de passe et lève un éventuel verrouillage."""
    verifier_politique(mot_de_passe)
    utilisateur = _obtenir(session, identifiant)
    utilisateur.mot_de_passe_hash = hacher_mot_de_passe(mot_de_passe)
    utilisateur.echecs_connexion = 0
    utilisateur.verrouille_jusqu_a = None
    session.commit()


def creer_admin_initial(session: Session) -> bool:
    """Crée le compte administrateur décrit par ``ADMIN_USERNAME`` / ``ADMIN_PASSWORD``.

    Utilisé au démarrage de l'API sur une base SQLite éphémère (Hugging Face), où
    aucun compte ne survit à un redémarrage. Sans effet si les variables sont absentes
    ou si le compte existe déjà.

    Returns:
        ``True`` si le compte a été créé.
    """
    identifiant, mot_de_passe = os.getenv("ADMIN_USERNAME"), os.getenv("ADMIN_PASSWORD")
    if not identifiant or not mot_de_passe or _trouver(session, identifiant) is not None:
        return False
    creer_utilisateur(session, identifiant, mot_de_passe, "admin")
    return True


def _trouver(session: Session, identifiant: str) -> Utilisateur | None:
    return session.scalars(select(Utilisateur).where(Utilisateur.identifiant == identifiant)).first()


def _obtenir(session: Session, identifiant: str) -> Utilisateur:
    utilisateur = _trouver(session, identifiant)
    if utilisateur is None:
        raise ValueError(f"aucun compte {identifiant!r}")
    return utilisateur


# ---------------------------------------------------------------- ligne de commande

def _lire_mot_de_passe(variable: str | None) -> str:
    if variable:
        if not (valeur := os.getenv(variable)):
            raise ValueError(f"la variable {variable} est vide ou absente")
        return valeur
    premier = getpass.getpass("Mot de passe : ")
    if premier != getpass.getpass("Confirmation : "):
        raise ValueError("les deux saisies diffèrent")
    return premier


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gestion des comptes de l'API.")
    commandes = parser.add_subparsers(dest="commande", required=True)

    creer = commandes.add_parser("creer", help="créer un compte")
    creer.add_argument("identifiant")
    creer.add_argument("--role", required=True, choices=ROLES)
    creer.add_argument("--mot-de-passe-env", metavar="NOM", help="variable contenant le mot de passe")

    mdp = commandes.add_parser("mot-de-passe", help="changer le mot de passe")
    mdp.add_argument("identifiant")
    mdp.add_argument("--mot-de-passe-env", metavar="NOM")

    commandes.add_parser("lister", help="lister les comptes")
    for nom in ("desactiver", "activer", "deverrouiller"):
        commandes.add_parser(nom).add_argument("identifiant")

    args = parser.parse_args(arguments)
    engine = creer_engine(get_database_url("ADMIN_DATABASE_URL"))
    try:
        with Session(engine) as session:
            if args.commande == "creer":
                creer_utilisateur(session, args.identifiant,
                                  _lire_mot_de_passe(args.mot_de_passe_env), args.role)
                print(f"Compte {args.identifiant!r} créé (rôle {args.role}).")
            elif args.commande == "mot-de-passe":
                changer_mot_de_passe(session, args.identifiant,
                                     _lire_mot_de_passe(args.mot_de_passe_env))
                print("Mot de passe modifié.")
            elif args.commande == "lister":
                for u in session.scalars(select(Utilisateur).order_by(Utilisateur.identifiant)):
                    etat = "actif" if u.actif else "désactivé"
                    print(f"{u.identifiant:<20} {u.role:<9} {etat:<10} "
                          f"dernière connexion : {u.derniere_connexion or '-'}")
            else:
                utilisateur = _obtenir(session, args.identifiant)
                if args.commande == "deverrouiller":
                    utilisateur.echecs_connexion, utilisateur.verrouille_jusqu_a = 0, None
                else:
                    utilisateur.actif = args.commande == "activer"
                session.commit()
                print(f"Compte {args.identifiant!r} : {args.commande} effectué.")
    except ValueError as erreur:
        print(f"Erreur : {erreur}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

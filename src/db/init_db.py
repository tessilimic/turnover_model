"""Crée le schéma et y charge la fusion des 3 CSV.

Usage : python -m src.db.init_db [--reset]
"""

import argparse
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from src.db.models import Employe, Prediction
from src.db.session import creer_schema, get_database_url, get_engine, supprimer_schema
from src.features import CIBLE, COLONNES_CONSTANTES, COLONNES_CORRELEES, COLONNES_ENTREE

DOSSIER_DONNEES = Path(__file__).resolve().parents[2] / "data"


def lire_csv(dossier: Path = DOSSIER_DONNEES) -> pd.DataFrame:
    """Fusionne et nettoie les 3 fichiers sources (1 ligne par employé)."""
    sirh = pd.read_csv(dossier / "extrait_sirh.csv")
    sondage = pd.read_csv(dossier / "extrait_sondage.csv", dtype={"code_sondage": str})
    evals = pd.read_csv(dossier / "extrait_eval.csv")

    sondage["id_employee"] = sondage["code_sondage"].astype(int)
    evals["id_employee"] = evals["eval_number"].str.replace("E_", "", regex=False).astype(int)

    df = sirh.merge(
        sondage.drop(columns="code_sondage"), on="id_employee", how="inner", validate="one_to_one"
    ).merge(
        evals.drop(columns="eval_number"), on="id_employee", how="inner", validate="one_to_one"
    )

    df = df.drop(columns=COLONNES_CONSTANTES + COLONNES_CORRELEES)
    # "11 %" -> 11
    df["augementation_salaire_precedente"] = (
        df["augementation_salaire_precedente"].str.replace("%", "").str.strip().astype(int)
    )
    return df


def charger_csv_en_base(engine: Engine, dossier: Path = DOSSIER_DONNEES) -> int:
    """Insère le jeu initial (entrées + départ observé). Renvoie le nombre de lignes ajoutées.

    Sans effet si le jeu initial est déjà en base.
    """
    with Session(engine) as session:
        deja_charges = session.scalar(
            select(func.count()).select_from(Employe).where(Employe.id_employee.is_not(None))
        )
        if deja_charges:
            return 0

        df = lire_csv(dossier)
        for ligne in df.to_dict(orient="records"):
            employe = Employe(
                id_employee=int(ligne["id_employee"]),
                **{col: _python(ligne[col]) for col in COLONNES_ENTREE},
            )
            employe.predictions.append(
                Prediction(origine="observation", depart=ligne[CIBLE] == "Oui")
            )
            session.add(employe)
        session.commit()
        return len(df)


def _python(valeur):
    """numpy.int64 -> int (certains pilotes refusent les types numpy)."""
    return valeur.item() if hasattr(valeur, "item") else valeur


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--reset", action="store_true",
        help="supprime les tables et TOUTES les données (prédictions comprises) avant de recharger",
    )
    args = parser.parse_args()

    engine = get_engine()
    print(f"Base : {engine.url.render_as_string(hide_password=True)}")
    if args.reset:
        supprimer_schema(engine)
        print("Tables supprimées.")
    creer_schema(engine)

    ajoutes = charger_csv_en_base(engine)
    print(f"Jeu initial : {ajoutes} employés ajoutés" if ajoutes else
          "Jeu initial déjà présent : rien à ajouter (--reset pour tout recharger).")


if __name__ == "__main__":
    main()

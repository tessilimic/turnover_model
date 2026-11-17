"""Fusion des 3 CSV (lire_csv), sur de petits fichiers temporaires."""

import pandas as pd
import pytest
from pandas.errors import MergeError

from src.db.init_db import DOSSIER_DONNEES, lire_csv
from src.features import CIBLE, COLONNES_CONSTANTES, COLONNES_CORRELEES, COLONNES_ENTREE

FICHIERS = ("extrait_sirh.csv", "extrait_sondage.csv", "extrait_eval.csv")


@pytest.fixture
def extraits(tmp_path):
    """Les 4 premiers employés de chaque fichier ; renvoie (dossier, DataFrames)."""
    dfs = {
        nom: pd.read_csv(DOSSIER_DONNEES / nom, dtype=str, keep_default_na=False).head(4)
        for nom in FICHIERS
    }

    def ecrire():
        for nom, df in dfs.items():
            df.to_csv(tmp_path / nom, index=False)
        return tmp_path

    return ecrire, dfs


def test_fusion_relie_les_lignes_par_identifiant_meme_dans_le_desordre(extraits):
    ecrire, dfs = extraits
    # Les évaluations dans l'ordre inverse : la fusion doit se faire sur l'id, pas sur la position.
    dfs["extrait_eval.csv"] = dfs["extrait_eval.csv"].iloc[::-1]
    sirh = dfs["extrait_sirh.csv"]

    df = lire_csv(ecrire())

    assert df["id_employee"].tolist() == sirh["id_employee"].astype(int).tolist()
    attendu = dfs["extrait_eval.csv"].assign(
        id=lambda d: d["eval_number"].str.removeprefix("E_").astype(int)
    ).set_index("id")["note_evaluation_precedente"].astype(int)
    assert df.set_index("id_employee")["note_evaluation_precedente"].to_dict() == attendu.to_dict()


def test_identifiants_convertis_depuis_les_3_formats(extraits):
    ecrire, dfs = extraits
    assert dfs["extrait_sondage.csv"]["code_sondage"].iloc[0] == "000001"
    assert dfs["extrait_eval.csv"]["eval_number"].iloc[0] == "E_1"

    df = lire_csv(ecrire())

    assert df["id_employee"].iloc[0] == 1
    assert "code_sondage" not in df and "eval_number" not in df


def test_pourcentage_converti_en_entier(extraits):
    ecrire, _ = extraits

    df = lire_csv(ecrire())

    assert df["augementation_salaire_precedente"].tolist()[0] == 11  # "11 %"
    assert pd.api.types.is_integer_dtype(df["augementation_salaire_precedente"])


def test_colonnes_constantes_et_correlees_retirees(extraits):
    ecrire, _ = extraits

    df = lire_csv(ecrire())

    assert set(df.columns) == set(COLONNES_ENTREE) | {"id_employee", CIBLE}
    assert not set(COLONNES_CONSTANTES + COLONNES_CORRELEES) & set(df.columns)


def test_employe_absent_d_un_fichier_est_ecarte(extraits):
    ecrire, dfs = extraits
    dfs["extrait_sondage.csv"] = dfs["extrait_sondage.csv"].iloc[1:]  # employé 1 sans sondage

    df = lire_csv(ecrire())

    assert len(df) == 3
    assert 1 not in df["id_employee"].tolist()


def test_doublon_d_identifiant_refuse(extraits):
    ecrire, dfs = extraits
    eval_ = dfs["extrait_eval.csv"]
    dfs["extrait_eval.csv"] = pd.concat([eval_, eval_.head(1)])  # E_1 en double

    with pytest.raises(MergeError):
        lire_csv(ecrire())

"""Modèles ORM (SQLAlchemy). Miroir de sql/01_schema.sql."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Employe(Base):
    """Entrées du modèle : jeu initial (id_employee renseigné) ou appel à /predict."""

    __tablename__ = "employes"

    id: Mapped[int] = mapped_column(primary_key=True)
    id_employee: Mapped[int | None] = mapped_column(unique=True)

    # SIRH
    age: Mapped[int]
    genre: Mapped[str] = mapped_column(String(1))
    revenu_mensuel: Mapped[int]
    statut_marital: Mapped[str] = mapped_column(String(50))
    departement: Mapped[str] = mapped_column(String(50))
    poste: Mapped[str] = mapped_column(String(50))
    nombre_experiences_precedentes: Mapped[int]
    annee_experience_totale: Mapped[int]
    annees_dans_le_poste_actuel: Mapped[int]
    # Sondage
    nombre_participation_pee: Mapped[int]
    nb_formations_suivies: Mapped[int]
    distance_domicile_travail: Mapped[int]
    niveau_education: Mapped[int]
    domaine_etude: Mapped[str] = mapped_column(String(50))
    frequence_deplacement: Mapped[str] = mapped_column(String(50))
    annees_depuis_la_derniere_promotion: Mapped[int]
    annes_sous_responsable_actuel: Mapped[int]
    # Évaluations
    satisfaction_employee_environnement: Mapped[int]
    note_evaluation_precedente: Mapped[int]
    satisfaction_employee_nature_travail: Mapped[int]
    satisfaction_employee_equipe: Mapped[int]
    satisfaction_employee_equilibre_pro_perso: Mapped[int]
    heure_supplementaires: Mapped[str] = mapped_column(String(3))
    augementation_salaire_precedente: Mapped[int]

    cree_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    predictions: Mapped[list["Prediction"]] = relationship(
        back_populates="employe", cascade="all, delete-orphan", passive_deletes=True
    )


class Prediction(Base):
    """Sortie : départ observé (jeu initial) ou prédit (avec probabilité et seuil)."""

    __tablename__ = "predictions"

    id: Mapped[int] = mapped_column(primary_key=True)
    employe_id: Mapped[int] = mapped_column(ForeignKey("employes.id", ondelete="CASCADE"))
    origine: Mapped[str] = mapped_column(String(11))
    depart: Mapped[bool]
    probabilite: Mapped[float | None]
    seuil: Mapped[float | None]
    cree_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    employe: Mapped[Employe] = relationship(back_populates="predictions")

    __table_args__ = (
        CheckConstraint("origine IN ('observation', 'prediction')", name="ck_predictions_origine"),
        CheckConstraint(
            "(origine = 'observation' AND probabilite IS NULL AND seuil IS NULL)"
            " OR (origine = 'prediction' AND probabilite IS NOT NULL AND seuil IS NOT NULL)",
            name="ck_predictions_valeurs",
        ),
        CheckConstraint(
            "probabilite IS NULL OR (probabilite >= 0 AND probabilite <= 1)",
            name="ck_predictions_probabilite",
        ),
        Index("ix_predictions_employe_id", "employe_id"),
        Index(
            "ux_predictions_une_observation",
            "employe_id",
            unique=True,
            postgresql_where=text("origine = 'observation'"),
            sqlite_where=text("origine = 'observation'"),
        ),
    )

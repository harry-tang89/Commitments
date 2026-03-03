import sqlalchemy as sa
import sqlalchemy.orm as so
from app import db
from typing import Optional
from datetime import date, datetime
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import login


commitment_collaborator = sa.Table(
    "commitment_collaborator",
    db.metadata,
    sa.Column("commitment_id", sa.ForeignKey("commitment.id", ondelete="CASCADE"), primary_key=True),
    sa.Column("user_id", sa.ForeignKey("user.id", ondelete="CASCADE"), primary_key=True),
    sa.Index("ix_commitment_collaborator_user_id", "user_id"),
)


@login.user_loader
def load_user(id):
    return db.session.get(User, int(id))


class User(UserMixin, db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    username: so.Mapped[str] = so.mapped_column(sa.String(64), index=True, unique=True)
    email: so.Mapped[str] = so.mapped_column(sa.String(120), index=True, unique=True)
    birth_day: so.Mapped[Optional[int]] = so.mapped_column(sa.Integer(), nullable=True)
    birth_month: so.Mapped[Optional[int]] = so.mapped_column(sa.Integer(), nullable=True)
    birth_year: so.Mapped[Optional[int]] = so.mapped_column(sa.Integer(), nullable=True)
    password_hash: so.Mapped[Optional[str]] = so.mapped_column(sa.String(256))
    commitments: so.Mapped[list["Commitment"]] = so.relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
    )
    joined_commitments: so.Mapped[list["Commitment"]] = so.relationship(
        secondary=commitment_collaborator,
        back_populates="collaborators",
    )

    def __repr__(self):
        return '<User {}'.format(self.username)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Commitment(db.Model):
    id: so.Mapped[int] = so.mapped_column(primary_key=True)
    user_id: so.Mapped[int] = so.mapped_column(sa.ForeignKey(User.id), index=True)
    category: so.Mapped[Optional[str]] = so.mapped_column(sa.String(32), nullable=True, index=True)
    title: so.Mapped[str] = so.mapped_column(sa.String(140))
    description: so.Mapped[Optional[str]] = so.mapped_column(sa.Text(), nullable=True)
    deadline_date: so.Mapped[date] = so.mapped_column(sa.Date(), index=True)
    status: so.Mapped[str] = so.mapped_column(sa.String(20), default="active")
    created_at: so.Mapped[datetime] = so.mapped_column(
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
    )
    owner: so.Mapped[User] = so.relationship(back_populates="commitments")
    collaborators: so.Mapped[list[User]] = so.relationship(
        secondary=commitment_collaborator,
        back_populates="joined_commitments",
    )

    def __repr__(self):
        return f"<Commitment {self.title}>"
